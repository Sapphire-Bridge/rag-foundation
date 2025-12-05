from __future__ import annotations

import os
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, Tuple

from .config import settings


def _build_genai_stub() -> Tuple[ModuleType, ModuleType, ModuleType]:
    """Create a minimal google.genai stub for tests and mock mode."""
    genai_mod = ModuleType("google.genai")
    types_mod = ModuleType("google.genai.types")
    errors_mod = ModuleType("google.genai.errors")

    class APIError(Exception):
        pass

    class ServerError(APIError):
        pass

    class ServiceUnavailable(ServerError):
        pass

    class DeadlineExceeded(ServerError):
        pass

    errors_mod.APIError = APIError
    errors_mod.ServerError = ServerError
    errors_mod.ServiceUnavailable = ServiceUnavailable
    errors_mod.DeadlineExceeded = DeadlineExceeded

    class Tool:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FileSearch:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class FileSearchStore:
        """Placeholder object; real calls use SDK instances."""

    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    types_mod.Tool = Tool
    types_mod.FileSearch = FileSearch
    types_mod.FileSearchStore = FileSearchStore
    types_mod.GenerateContentConfig = GenerateContentConfig

    class _DummyModels:
        def __init__(self):
            self.generate_content = lambda *args, **kwargs: SimpleNamespace()
            self.generate_content_stream = lambda *args, **kwargs: []

    class _DummyStores:
        def list(self):
            return []

        def create(self, config):
            return SimpleNamespace(name="stores/mock")

        def upload_to_file_search_store(self, **kwargs):
            return SimpleNamespace(name="operations/mock")

    class _DummyOperations:
        def get(self, *_args, **_kwargs):
            return SimpleNamespace(done=True, error=None)

    class Client:
        def __init__(self, *args, **kwargs):
            self.file_search_stores = _DummyStores()
            self.models = _DummyModels()
            self.operations = _DummyOperations()

    genai_mod.Client = Client
    genai_mod.errors = errors_mod
    genai_mod.types = types_mod

    return genai_mod, types_mod, errors_mod


USE_GENAI_STUB = (
    (settings.GEMINI_MOCK_MODE and settings.ENVIRONMENT in {"development", "test"})
    or os.environ.get("USE_GOOGLE_GENAI_STUB") == "1"
    or os.environ.get("USE_GENAI_STUB") == "1"
)

if USE_GENAI_STUB:
    genai_module, types_module, errors_module = _build_genai_stub()
else:
    try:
        from google import genai as genai_module  # type: ignore
        from google.genai import types as types_module, errors as errors_module  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Failed to import google.genai. Set USE_GOOGLE_GENAI_STUB=1 to run without the SDK (mock mode only)."
        ) from exc

genai = genai_module
types = types_module
errors = errors_module


def redact_llm_error(exc: BaseException | None) -> Dict[str, Any]:
    """
    Return a scrubbed view of an upstream LLM error that omits prompts/content.
    """
    if exc is None:
        return {}
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None) if response is not None else None
    return {
        "error_type": type(exc).__name__,
        "error_code": getattr(exc, "code", None) or getattr(exc, "status", None),
        "status_code": status_code,
        "detail": "[REDACTED]",
    }


__all__ = ["genai", "types", "errors", "USE_GENAI_STUB", "redact_llm_error"]
