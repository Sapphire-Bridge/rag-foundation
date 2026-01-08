from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.file_types import (
    ALL_SUPPORTED_UPLOAD_MIMES,
    OFFICE_UPLOAD_MIMES,
    SAFE_DEFAULT_UPLOAD_MIMES,
)


def _base_kwargs() -> dict[str, Any]:
    return {
        "GEMINI_API_KEY": "test-key-12345678901234567890",
        "JWT_SECRET": "x" * 64,
    }


def test_safe_profile_uses_conservative_set():
    s = Settings(**_base_kwargs(), UPLOAD_PROFILE="safe")
    assert set(s.ALLOWED_UPLOAD_MIMES) == SAFE_DEFAULT_UPLOAD_MIMES


def test_office_profile_includes_excel_and_word():
    s = Settings(**_base_kwargs(), UPLOAD_PROFILE="office")
    allowed = set(s.ALLOWED_UPLOAD_MIMES)
    assert "application/vnd.ms-excel" in allowed
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in allowed
    assert allowed == set(OFFICE_UPLOAD_MIMES)


def test_all_supported_profile_matches_canonical_set():
    s = Settings(**_base_kwargs(), UPLOAD_PROFILE="all-supported")
    assert set(s.ALLOWED_UPLOAD_MIMES) == ALL_SUPPORTED_UPLOAD_MIMES


def test_custom_profile_rejects_unknown_mimes():
    with pytest.raises(ValueError):
        Settings(
            **_base_kwargs(),
            UPLOAD_PROFILE="custom",
            ALLOWED_UPLOAD_MIMES=["application/pdf", "application/not-real-type"],
        )


def test_custom_profile_normalizes_case():
    s = Settings(
        **_base_kwargs(),
        UPLOAD_PROFILE="custom",
        ALLOWED_UPLOAD_MIMES=["Application/PDF", "text/Markdown"],
    )
    assert s.ALLOWED_UPLOAD_MIMES == ["application/pdf", "text/markdown"]
