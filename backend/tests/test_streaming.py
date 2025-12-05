import time

from fastapi.testclient import TestClient
from types import SimpleNamespace
from unittest.mock import Mock, patch, MagicMock

import app.routes.chat as chat_routes
from app.config import settings
from app.main import app
from app.auth import get_current_user as real_get_current_user, get_authorization as real_get_authorization
from app.db import get_db as real_get_db


class TestChatStreamingResilience:
    """Test chat endpoint streaming retry logic."""

    def test_chat_streaming_retries_on_transient_errors(self):
        """Verify streaming endpoint retries on ServiceUnavailable."""
        client = TestClient(app)
        mock_user = Mock(id=1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user
        orig_session_local = chat_routes.SessionLocal
        chat_routes.get_current_user = lambda db, token: mock_user
        mock_db = MagicMock()
        chat_routes.SessionLocal = lambda: mock_db
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db():
            yield mock_db

        app.dependency_overrides[real_get_db] = _ov_db
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
        finally:
            chat_routes.get_current_user = orig_get_current_user
            chat_routes.SessionLocal = orig_session_local
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)

    def test_chat_streaming_exhausts_retries_on_persistent_errors(self):
        """Verify streaming endpoint gives up after max retries."""
        client = TestClient(app)
        mock_user = Mock(id=1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user
        orig_session_local = chat_routes.SessionLocal
        chat_routes.get_current_user = lambda db, token: mock_user
        mock_db = MagicMock()
        chat_routes.SessionLocal = lambda: mock_db
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db2():
            yield mock_db

        app.dependency_overrides[real_get_db] = _ov_db2
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
                    assert "error" in content
                    assert "Service temporarily unavailable" in content
        finally:
            chat_routes.get_current_user = orig_get_current_user
            chat_routes.SessionLocal = orig_session_local
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)

    def test_chat_streaming_handles_unexpected_errors(self):
        """Verify streaming endpoint handles non-retryable errors."""
        client = TestClient(app)
        mock_user = Mock(id=1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user
        orig_session_local = chat_routes.SessionLocal
        chat_routes.get_current_user = lambda db, token: mock_user
        mock_db = MagicMock()
        chat_routes.SessionLocal = lambda: mock_db
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db3():
            yield mock_db

        app.dependency_overrides[real_get_db] = _ov_db3
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
                    assert "error" in content
                    assert "An error occurred processing your request. Please try again." in content
        finally:
            chat_routes.get_current_user = orig_get_current_user
            chat_routes.SessionLocal = orig_session_local
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)

    def test_chat_streaming_emits_keepalive(self, monkeypatch):
        """Keepalive frames should be sent when no chunks arrive for a while."""
        client = TestClient(app)
        mock_user = Mock(id=1)
        app.dependency_overrides[real_get_authorization] = lambda: "test-token"
        app.dependency_overrides[real_get_current_user] = lambda: mock_user
        orig_get_current_user = chat_routes.get_current_user
        orig_session_local = chat_routes.SessionLocal
        chat_routes.get_current_user = lambda db, token: mock_user
        mock_db = MagicMock()
        chat_routes.SessionLocal = lambda: mock_db
        mock_db.query.return_value.filter.return_value.one_or_none.return_value = None

        def _ov_db():
            yield mock_db

        app.dependency_overrides[real_get_db] = _ov_db

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
            chat_routes.SessionLocal = orig_session_local
            app.dependency_overrides.pop(real_get_authorization, None)
            app.dependency_overrides.pop(real_get_current_user, None)
            app.dependency_overrides.pop(real_get_db, None)
