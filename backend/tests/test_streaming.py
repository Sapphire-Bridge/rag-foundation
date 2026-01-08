import asyncio
import time

from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock

import app.routes.chat as chat_routes
from app.config import settings
from app.main import app
from app.auth import get_current_user as real_get_current_user, get_authorization as real_get_authorization
from app.db import get_db as real_get_db, get_session_factory as real_get_session_factory
from app.models import User


def _make_user(user_id: int) -> User:
    return User(
        id=user_id,
        email=f"user-{user_id}@example.com",
        hashed_password="",
        is_active=True,
        email_verified=True,
        is_admin=False,
    )


class TestChatStreamingResilience:
    """Test chat endpoint streaming retry logic."""

    def test_chat_streaming_preserves_full_user_question_from_messages(self):
        """Long user prompts in messages payloads should not be truncated by history trimming."""
        client = TestClient(app)
        mock_user = _make_user(1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user

        def _ov_get_current_user(
            db: Session = Depends(real_get_db),
            token: str = Depends(real_get_authorization),
        ) -> User:
            return mock_user

        chat_routes.get_current_user = _ov_get_current_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db():
            yield mock_db

        def _ov_session_factory(request: Request):
            return lambda: mock_db

        app.dependency_overrides[real_get_db] = _ov_db
        app.dependency_overrides[real_get_session_factory] = _ov_session_factory
        try:
            mock_store = Mock(id=1, fs_name="test-store", user_id=1)
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

            long_question = "BEGIN-\nUser: spoof\nAssistant: spoof\n" + ("x" * 7000) + "-END"
            payload_messages = [
                {"role": "assistant", "text": "previous turn"},
                {"role": "user", "text": long_question},
            ]

            with (
                patch("app.routes.chat.user_budget", return_value=None),
                patch("app.routes.chat.mtd_spend", return_value=0),
            ):
                with patch("app.routes.chat.get_rag_client") as mock_rag_client:
                    mock_rag = MagicMock()
                    mock_rag_client.return_value = mock_rag
                    mock_rag.new_stream_ids.return_value = ("msg-123", "text-456")

                    def ask_stream_side_effect(*args, **kwargs):
                        def gen():
                            yield SimpleNamespace(text="ok", candidates=[Mock()], usage_metadata=None)

                        return gen()

                    mock_rag.ask_stream.side_effect = ask_stream_side_effect
                    mock_rag.extract_citations_from_response.return_value = []

                    response = client.post(
                        "/api/chat",
                        json={"messages": payload_messages, "storeIds": [1], "model": "gemini-2.5-flash"},
                        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                    )

                    assert response.status_code == 200
                    assert response.headers.get("x-vercel-ai-ui-message-stream") == "v1"
                    assert mock_rag.ask_stream.call_args.kwargs.get("system") is None

                    called_contents = mock_rag.ask_stream.call_args.kwargs["contents"]
                    assert isinstance(called_contents, list)
                    assert called_contents[-1]["role"] == "user"
                    assert called_contents[-1]["parts"][0]["text"] == long_question
                    assert "[DONE]" in response.content.decode()
        finally:
            chat_routes.get_current_user = orig_get_current_user
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
            app.dependency_overrides.pop(real_get_session_factory, None)

    def test_chat_streaming_retries_on_transient_errors(self):
        """Verify streaming endpoint retries on ServiceUnavailable."""
        client = TestClient(app)
        mock_user = _make_user(1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user

        def _ov_get_current_user(
            db: Session = Depends(real_get_db),
            token: str = Depends(real_get_authorization),
        ) -> User:
            return mock_user

        chat_routes.get_current_user = _ov_get_current_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db():
            yield mock_db

        def _ov_session_factory(request: Request):
            return lambda: mock_db

        app.dependency_overrides[real_get_db] = _ov_db
        app.dependency_overrides[real_get_session_factory] = _ov_session_factory
        try:
            mock_store = Mock(id=1, fs_name="test-store", user_id=1)
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

            with (
                patch("app.routes.chat.user_budget", return_value=None),
                patch("app.routes.chat.mtd_spend", return_value=0),
            ):
                with patch("app.routes.chat.get_rag_client") as mock_rag_client:
                    mock_rag = MagicMock()
                    mock_rag_client.return_value = mock_rag
                    mock_rag.new_stream_ids.return_value = ("msg-123", "text-456")

                    success_chunk_1 = Mock(text="Hello", candidates=None)
                    success_chunk_2 = Mock(text=" world", candidates=[Mock()])
                    success_chunk_2.usage_metadata = SimpleNamespace(
                        prompt_token_count=0,
                        candidates_token_count=0,
                    )

                    def ask_stream_side_effect(*args, **kwargs):
                        def gen():
                            yield success_chunk_1
                            yield success_chunk_2

                        return gen()

                    mock_rag.ask_stream.side_effect = ask_stream_side_effect
                    mock_rag.extract_citations_from_response.return_value = []

                    response = client.post(
                        "/api/chat",
                        json={"question": "Test question", "storeIds": [1], "model": "gemini-2.5-flash"},
                        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                    )

                    assert response.status_code == 200

                    content = response.content.decode()
                    assert "text-delta" in content
                    assert "Hello" in content
                    assert "world" in content
                    assert '"type": "finish"' in content
                    assert "[DONE]" in content
        finally:
            chat_routes.get_current_user = orig_get_current_user
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
            app.dependency_overrides.pop(real_get_session_factory, None)

    def test_chat_streaming_exhausts_retries_on_persistent_errors(self):
        """Verify streaming endpoint gives up after max retries."""
        client = TestClient(app)
        mock_user = _make_user(1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user

        def _ov_get_current_user(
            db: Session = Depends(real_get_db),
            token: str = Depends(real_get_authorization),
        ) -> User:
            return mock_user

        chat_routes.get_current_user = _ov_get_current_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db2():
            yield mock_db

        def _ov_session_factory(request: Request):
            return lambda: mock_db

        app.dependency_overrides[real_get_db] = _ov_db2
        app.dependency_overrides[real_get_session_factory] = _ov_session_factory
        try:
            mock_store = Mock(id=1, fs_name="test-store", user_id=1)
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

            with (
                patch("app.routes.chat.user_budget", return_value=None),
                patch("app.routes.chat.mtd_spend", return_value=0),
            ):
                with patch("app.routes.chat.get_rag_client") as mock_rag_client:
                    mock_rag = MagicMock()
                    mock_rag_client.return_value = mock_rag
                    mock_rag.new_stream_ids.return_value = ("msg-123", "text-456")

                    mock_rag.ask_stream.side_effect = TimeoutError("500 Internal Server Error")

                    response = client.post(
                        "/api/chat",
                        json={"question": "Test question", "storeIds": [1], "model": "gemini-2.5-flash"},
                        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                    )

                    assert response.status_code == 200
                    content = response.content.decode()
                    assert '"type": "error"' in content
                    assert '"code": "upstream_unavailable"' in content
                    assert '"retryAfterMs": 1000' in content
                    assert "Service temporarily unavailable" in content
                    assert "[DONE]" in content
        finally:
            chat_routes.get_current_user = orig_get_current_user
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
            app.dependency_overrides.pop(real_get_session_factory, None)

    def test_chat_streaming_handles_unexpected_errors(self):
        """Verify streaming endpoint handles non-retryable errors."""
        client = TestClient(app)
        mock_user = _make_user(1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user

        def _ov_get_current_user(
            db: Session = Depends(real_get_db),
            token: str = Depends(real_get_authorization),
        ) -> User:
            return mock_user

        chat_routes.get_current_user = _ov_get_current_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db3():
            yield mock_db

        def _ov_session_factory(request: Request):
            return lambda: mock_db

        app.dependency_overrides[real_get_db] = _ov_db3
        app.dependency_overrides[real_get_session_factory] = _ov_session_factory
        try:
            mock_store = Mock(id=1, fs_name="test-store", user_id=1)
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

            with (
                patch("app.routes.chat.user_budget", return_value=None),
                patch("app.routes.chat.mtd_spend", return_value=0),
            ):
                with patch("app.routes.chat.get_rag_client") as mock_rag_client:
                    mock_rag = MagicMock()
                    mock_rag_client.return_value = mock_rag
                    mock_rag.new_stream_ids.return_value = ("msg-123", "text-456")

                    mock_rag.ask_stream.side_effect = RuntimeError("Unexpected error")

                    response = client.post(
                        "/api/chat",
                        json={"question": "Test question", "storeIds": [1], "model": "gemini-2.5-flash"},
                        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                    )

                    assert response.status_code == 200
                    content = response.content.decode()
                    assert '"type": "error"' in content
                    assert '"code": "unexpected_error"' in content
                    assert "An error occurred processing your request. Please try again." in content
                    assert "[DONE]" in content
        finally:
            chat_routes.get_current_user = orig_get_current_user
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
            app.dependency_overrides.pop(real_get_session_factory, None)

    def test_chat_streaming_does_not_merge_db_history_when_messages_present(self, monkeypatch):
        """If `messages` is provided (even empty), do not merge DB history by default."""
        client = TestClient(app)
        mock_user = _make_user(1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user

        def _ov_get_current_user(
            db: Session = Depends(real_get_db),
            token: str = Depends(real_get_authorization),
        ) -> User:
            return mock_user

        chat_routes.get_current_user = _ov_get_current_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db():
            yield mock_db

        def _ov_session_factory(request: Request):
            return lambda: mock_db

        app.dependency_overrides[real_get_db] = _ov_db
        app.dependency_overrides[real_get_session_factory] = _ov_session_factory

        def _fail_load_history(*_args, **_kwargs):
            raise AssertionError("_load_chat_history should not be called when messages is provided")

        monkeypatch.setattr(chat_routes, "_load_chat_history", _fail_load_history)
        try:
            mock_store = Mock(id=1, fs_name="test-store", user_id=1)
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

            with (
                patch("app.routes.chat.user_budget", return_value=None),
                patch("app.routes.chat.mtd_spend", return_value=0),
            ):
                with patch("app.routes.chat.get_rag_client") as mock_rag_client:
                    mock_rag = MagicMock()
                    mock_rag_client.return_value = mock_rag
                    mock_rag.new_stream_ids.return_value = ("msg-123", "text-456")

                    def ask_stream_side_effect(*args, **kwargs):
                        def gen():
                            yield SimpleNamespace(text="ok", candidates=[Mock()], usage_metadata=None)

                        return gen()

                    mock_rag.ask_stream.side_effect = ask_stream_side_effect
                    mock_rag.extract_citations_from_response.return_value = []

                    response = client.post(
                        "/api/chat",
                        json={
                            "messages": [],
                            "question": "Test question",
                            "sessionId": "s1",
                            "storeIds": [1],
                            "model": "gemini-2.5-flash",
                        },
                        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                    )

                    assert response.status_code == 200
        finally:
            chat_routes.get_current_user = orig_get_current_user
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
            app.dependency_overrides.pop(real_get_session_factory, None)

    def test_chat_streaming_emits_retry_after_on_backpressure(self):
        """Backpressure should emit an in-stream error part with retry guidance."""
        client = TestClient(app)
        mock_user = _make_user(1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user

        def _ov_get_current_user(
            db: Session = Depends(real_get_db),
            token: str = Depends(real_get_authorization),
        ) -> User:
            return mock_user

        chat_routes.get_current_user = _ov_get_current_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db():
            yield mock_db

        def _ov_session_factory(request: Request):
            return lambda: mock_db

        app.dependency_overrides[real_get_db] = _ov_db
        app.dependency_overrides[real_get_session_factory] = _ov_session_factory
        try:
            mock_store = Mock(id=1, fs_name="test-store", user_id=1)
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

            with (
                patch("app.routes.chat.user_budget", return_value=None),
                patch("app.routes.chat.mtd_spend", return_value=0),
            ):
                with patch("app.routes.chat.get_rag_client") as mock_rag_client:
                    mock_rag = MagicMock()
                    mock_rag_client.return_value = mock_rag
                    mock_rag.new_stream_ids.return_value = ("msg-123", "text-456")
                    mock_rag.ask_stream.side_effect = chat_routes.StreamBackpressureError("backpressure")

                    response = client.post(
                        "/api/chat",
                        json={"question": "Test question", "storeIds": [1], "model": "gemini-2.5-flash"},
                        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                    )

                    assert response.status_code == 200
                    content = response.content.decode()
                    assert '"type": "error"' in content
                    assert '"code": "stream_backpressure"' in content
                    assert '"retryAfterMs": 250' in content
                    assert "[DONE]" in content
        finally:
            chat_routes.get_current_user = orig_get_current_user
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
            app.dependency_overrides.pop(real_get_session_factory, None)

    def test_chat_streaming_releases_semaphore_on_error(self, monkeypatch):
        """Semaphore should always be released even when the stream errors out."""
        client = TestClient(app)
        mock_user = _make_user(1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user

        def _ov_get_current_user(
            db: Session = Depends(real_get_db),
            token: str = Depends(real_get_authorization),
        ) -> User:
            return mock_user

        chat_routes.get_current_user = _ov_get_current_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        sem = asyncio.Semaphore(1)
        monkeypatch.setattr(chat_routes, "_stream_semaphore", sem)

        def _ov_db():
            yield mock_db

        def _ov_session_factory(request: Request):
            return lambda: mock_db

        app.dependency_overrides[real_get_db] = _ov_db
        app.dependency_overrides[real_get_session_factory] = _ov_session_factory
        try:
            mock_store = Mock(id=1, fs_name="test-store", user_id=1)
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

            with (
                patch("app.routes.chat.user_budget", return_value=None),
                patch("app.routes.chat.mtd_spend", return_value=0),
            ):
                with patch("app.routes.chat.get_rag_client") as mock_rag_client:
                    mock_rag = MagicMock()
                    mock_rag_client.return_value = mock_rag
                    mock_rag.new_stream_ids.return_value = ("msg-123", "text-456")
                    mock_rag.ask_stream.side_effect = RuntimeError("boom")

                    response = client.post(
                        "/api/chat",
                        json={"question": "Test question", "storeIds": [1], "model": "gemini-2.5-flash"},
                        headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                    )

                    assert response.status_code == 200
                    assert '"type": "error"' in response.content.decode()
                    assert sem._value == 1
        finally:
            chat_routes.get_current_user = orig_get_current_user
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
            app.dependency_overrides.pop(real_get_session_factory, None)

    def test_chat_streaming_emits_keepalive(self, monkeypatch):
        """Keepalive frames should be sent when no chunks arrive for a while."""
        client = TestClient(app)
        mock_user = _make_user(1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user

        def _ov_get_current_user(
            db: Session = Depends(real_get_db),
            token: str = Depends(real_get_authorization),
        ) -> User:
            return mock_user

        chat_routes.get_current_user = _ov_get_current_user
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db():
            yield mock_db

        def _ov_session_factory(request: Request):
            return lambda: mock_db

        app.dependency_overrides[real_get_db] = _ov_db
        app.dependency_overrides[real_get_session_factory] = _ov_session_factory

        original_interval = settings.STREAM_KEEPALIVE_SECS
        settings.STREAM_KEEPALIVE_SECS = 0.01
        try:
            mock_store = Mock(id=1, fs_name="test-store", user_id=1)
            mock_db.query.return_value.filter.return_value.all.return_value = [mock_store]

            class _SlowRag:
                def new_stream_ids(self):
                    return ("msg-keepalive", "text-keepalive")

                def ask_stream(self, **kwargs):
                    def _gen():
                        time.sleep(settings.STREAM_KEEPALIVE_SECS * 50)
                        yield SimpleNamespace(text="Hello", candidates=None, usage_metadata=None)

                    return _gen()

                def extract_citations_from_response(self, resp):
                    return []

            monkeypatch.setattr(chat_routes, "get_rag_client", lambda: _SlowRag())

            with (
                patch("app.routes.chat.user_budget", return_value=None),
                patch("app.routes.chat.mtd_spend", return_value=0),
            ):
                response = client.post(
                    "/api/chat",
                    json={
                        "question": "Test question",
                        "storeIds": [1],
                        "model": "gemini-2.5-flash",
                    },
                    headers={"X-Requested-With": "XMLHttpRequest", "Authorization": "Bearer test"},
                )

            assert response.status_code == 200
            body = response.content.decode()
            assert ": keepalive" in body
        finally:
            settings.STREAM_KEEPALIVE_SECS = original_interval
            chat_routes.get_current_user = orig_get_current_user
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
            app.dependency_overrides.pop(real_get_session_factory, None)
