from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routes.chat import (
    _build_history_prompt,
    _estimate_tokens_from_text,
    _extract_message_text,
    _sanitize_session_id,
    _sanitize_tags,
    _trim_title,
)


def test_extract_message_text_prefers_nested_content():
    msg = {"content": [{"text": "hello"}, {"text": "ignored"}]}
    assert _extract_message_text(msg) == "hello ignored"


def test_build_history_prompt_tracks_last_user_and_transcript():
    transcript, last_user = _build_history_prompt(
        [
            {"role": "user", "text": "hi"},
            {"role": "assistant", "text": "there"},
            {"role": "user", "text": "again"},
        ]
    )
    assert "User: hi" in transcript and "Assistant: there" in transcript
    assert last_user == "again"


def test_sanitize_tags_filters_invalid_entries():
    with pytest.raises(HTTPException):
        _sanitize_tags(["bad"])  # type: ignore[arg-type]

    tags = _sanitize_tags({"": "skip", "ok": "value", "num": 3, "nested": {"bad": True}})
    assert tags == {"ok": "value", "num": "3"}


def test_trim_and_session_id_helpers():
    long_title = "x" * 80
    assert _trim_title(long_title).endswith("…")

    sid = _sanitize_session_id(" " + "y" * 70)
    assert len(sid) <= 64
    assert sid.strip() == sid


def test_estimate_tokens_from_text_counts_chunks():
    assert _estimate_tokens_from_text("abcd") == 1
    assert _estimate_tokens_from_text("a" * 20) >= 5
