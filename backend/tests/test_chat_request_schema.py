import pytest
from pydantic import ValidationError

from app.routes.chat import ChatRequest


def test_chat_request_accepts_camelcase() -> None:
    req = ChatRequest.model_validate(
        {"storeIds": [1], "sessionId": "s1", "metadataFilter": {"a": "b"}, "projectId": 123}
    )
    assert req.storeIds == [1]
    assert req.sessionId == "s1"
    assert req.metadataFilter == {"a": "b"}
    assert req.projectId == 123


def test_chat_request_accepts_snakecase() -> None:
    req = ChatRequest.model_validate(
        {"store_ids": [1], "session_id": "s1", "metadata_filter": {"a": "b"}, "project_id": 123}
    )
    assert req.storeIds == [1]
    assert req.sessionId == "s1"
    assert req.metadataFilter == {"a": "b"}
    assert req.projectId == 123


def test_chat_request_accepts_system_and_tools() -> None:
    req = ChatRequest.model_validate({"storeIds": [1], "messages": [], "system": "sys", "tools": [{"name": "t"}]})
    assert req.system == "sys"
    assert req.tools == [{"name": "t"}]


def test_chat_request_rejects_snake_and_camel_conflicts() -> None:
    with pytest.raises(ValidationError, match="storeIds.*store_ids"):
        ChatRequest.model_validate({"storeIds": [2], "store_ids": [1]})
    with pytest.raises(ValidationError, match="sessionId.*session_id"):
        ChatRequest.model_validate({"storeIds": [1], "sessionId": "s1", "session_id": "s2"})
