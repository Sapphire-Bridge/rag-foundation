# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import time
import uuid
import logging
from dataclasses import dataclass
from typing import Optional, Sequence, List, Dict, Union, Generator, Any
from types import SimpleNamespace
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from ..config import settings
from ..genai import genai, types, errors
from ..metrics import gemini_calls_total, gemini_latency

logger = logging.getLogger(__name__)

RETRYABLE_GENAI_ERRORS = (
    errors.ServerError,
    getattr(errors, "ServiceUnavailable", errors.ServerError),
    getattr(errors, "DeadlineExceeded", errors.ServerError),
)
RETRYABLE_EXCEPTIONS = RETRYABLE_GENAI_ERRORS + (
    errors.APIError,
    httpx.HTTPStatusError,
    TimeoutError,
    httpx.TimeoutException,
)


@dataclass
class UploadResult:
    operation_name: str
    file_id: str | None = None


def _is_rate_limit_error(exc: BaseException | None) -> bool:
    if isinstance(exc, errors.APIError) and getattr(exc, "code", None) == 429:
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return True
    return False


def _is_retryable_error(exc: BaseException) -> bool:
    if isinstance(exc, RETRYABLE_GENAI_ERRORS):
        return True
    if isinstance(exc, errors.APIError):
        return getattr(exc, "code", None) in {429, 500, 502, 503}
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503}
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return True
    return False


def _wait_strategy(retry_state: Any) -> float:
    exc = retry_state.outcome.exception()
    if _is_rate_limit_error(exc):
        return wait_exponential(multiplier=2, min=4, max=30)(retry_state)
    return wait_exponential(multiplier=0.5, min=1, max=10)(retry_state)


def _before_sleep_log(retry_state: Any) -> None:
    exc = retry_state.outcome.exception()
    logger.warning(
        "Retrying Gemini call",
        extra={
            "attempt": retry_state.attempt_number,
            "is_rate_limit": _is_rate_limit_error(exc),
            "error_type": type(exc).__name__ if exc else None,
        },
    )


def _gemini_retry() -> Any:
    """Provide a consistent retry decorator for Gemini operations."""
    return retry(
        stop=stop_after_attempt(settings.GEMINI_RETRY_ATTEMPTS),
        wait=_wait_strategy,
        retry=retry_if_exception(_is_retryable_error),
        reraise=True,
        before_sleep=_before_sleep_log,
    )


def _get_response_name(response: Any, *, context: str) -> str:
    if isinstance(response, str):
        return response
    name = response.get("name") if isinstance(response, dict) else getattr(response, "name", None)
    if not name:
        raise ValueError(f"Missing name in {context} response")
    return name


def _extract_error_message(err: Any) -> Optional[str]:
    """Extract human-readable error message from various formats."""
    if err is None:
        return None

    if isinstance(err, str):
        return err

    if isinstance(err, dict):
        return err.get("message") or err.get("msg") or err.get("error") or err.get("details") or str(err)

    msg = getattr(err, "message", None)
    if msg:
        return str(msg)

    msg = getattr(err, "msg", None)
    if msg:
        return str(msg)

    return str(err)


def _normalize_operation_result(op: Any, *, name: str, context: str) -> dict:
    if isinstance(op, dict):
        return {
            "name": op.get("name", name),
            "done": bool(op.get("done", False)),
            "metadata": op.get("metadata", {}) or {},
            "error": _extract_error_message(op.get("error")),
        }

    if isinstance(op, str):
        logger.error(
            "operations.get returned unexpected string",
            extra={"op_name": name, "response": op, "context": context},
        )
        raise ValueError(f"Unexpected string response from operations.get: {op}")

    try:
        return {
            "name": getattr(op, "name", name) or name,
            "done": bool(getattr(op, "done", False)),
            "metadata": getattr(op, "metadata", {}) or {},
            "error": _extract_error_message(getattr(op, "error", None)),
        }
    except AttributeError as exc:
        logger.error(
            "operations.get returned object without expected attributes",
            extra={"op_name": name, "op_type": type(op).__name__, "context": context, "error": str(exc)},
        )
        raise ValueError(f"Invalid operation object type: {type(op)}") from exc


def _extract_uploaded_file_id(op: Any) -> str | None:
    """Best-effort extraction of the Gemini file identifier from upload responses."""
    try:
        # Some SDKs return the file object directly (name like "files/xyz")
        direct_name = getattr(op, "name", None)
        if isinstance(direct_name, str) and direct_name.strip().startswith("files/"):
            return direct_name

        # Newer SDKs wrap the file under `file` (UploadFileResponse.file.name)
        file_obj = getattr(op, "file", None)
        if file_obj:
            name = getattr(file_obj, "name", None) or getattr(file_obj, "id", None)
            if isinstance(name, str) and name.strip():
                return name

        # Some SDK responses use `result.file.name`
        result_obj = getattr(op, "result", None)
        if result_obj:
            nested_file = getattr(result_obj, "file", None)
            if nested_file:
                name = getattr(nested_file, "name", None) or getattr(nested_file, "id", None)
                if isinstance(name, str) and name.strip():
                    return name

        # Some Operation objects expose a `response` attr with the file
        resp_obj = getattr(op, "response", None)
        if resp_obj:
            resp_file = getattr(resp_obj, "file", None)
            if resp_file:
                name = getattr(resp_file, "name", None) or getattr(resp_file, "id", None)
                if isinstance(name, str) and name.strip():
                    return name
            resp_name = getattr(resp_obj, "name", None)
            if isinstance(resp_name, str) and resp_name.startswith("files/"):
                return resp_name

        metadata = getattr(op, "metadata", None) if not isinstance(op, dict) else op.get("metadata")
        if isinstance(metadata, dict):
            file_info = metadata.get("file") or metadata.get("resource") or metadata.get("fileInfo")
            if isinstance(file_info, dict):
                name = (
                    file_info.get("name") or file_info.get("id") or file_info.get("file_id") or file_info.get("fileId")
                )
                if isinstance(name, str) and name.strip():
                    return name

            # Some operations return a resourceName directly
            resource_name = metadata.get("resourceName") or metadata.get("resource_name")
            if isinstance(resource_name, str) and resource_name.startswith("files/"):
                return resource_name

        # Some clients return a dict with top-level "file"
        if isinstance(op, dict):
            file_info = (
                op.get("file") or op.get("result", {}).get("file") if isinstance(op.get("result"), dict) else None
            )
            if isinstance(file_info, dict):
                name = (
                    file_info.get("name") or file_info.get("id") or file_info.get("file_id") or file_info.get("fileId")
                )
                if isinstance(name, str) and name.strip():
                    return name
    except Exception as exc:
        logging.warning(
            "Exception during file_id extraction",
            extra={"error": str(exc), "response_type": type(op).__name__},
        )
        return None
    try:
        top_level = list(vars(op).keys())[:10] if hasattr(op, "__dict__") else "no_dict"
    except Exception:
        top_level = "unavailable"
    logging.warning(
        "Could not extract file_id from upload response",
        extra={
            "response_type": type(op).__name__,
            "has_file_attr": hasattr(op, "file"),
            "has_metadata_attr": hasattr(op, "metadata"),
            "top_level_attrs": top_level,
        },
    )
    return None


class GeminiRag:
    """
    Managed RAG via Gemini File Search.

    Features:
    - Timeouts: Configurable via GEMINI_HTTP_TIMEOUT_S
    - Retries: ask() auto-retries ServerError/ServiceUnavailable/TimeoutError
    - Metrics: Prometheus counters/histograms for observability
    - Citation extraction: Best-effort parsing with logging on failures

    Limitations:
    - ask_stream() does NOT auto-retry (caller must implement retry logic)
    - Citation parsing uses defensive getattr() chains (no schema validation)
    - ask_stream() is synchronous and may block async event loops

    Thread-safety: Safe for concurrent use (underlying client is thread-safe)
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        # Intentionally omit explicit HTTP timeouts; streaming can surpass 60s and should not be cut off.
        self.client = genai.Client(api_key=api_key)
        # Retain API key for REST fallback on rare SDK timeout issues
        self._api_key = api_key
        self.is_mock = False

    # -------- Stores --------
    def list_stores(self) -> List[types.FileSearchStore]:
        return list(self.client.file_search_stores.list())

    @_gemini_retry()
    def create_store(self, display_name: str) -> str:
        """
        Create a File Search store. Primary path uses the SDK; on specific
        timeout issues, fall back to direct REST call which we know succeeds
        in constrained environments.
        """
        try:
            s = self.client.file_search_stores.create(config={"display_name": display_name})
            return _get_response_name(s, context="store creation")
        except Exception as e:
            # If we have an API key, attempt REST fallback for resilience
            # Only for timeouts/transport issues; otherwise re-raise
            from httpx import ReadTimeout, TimeoutException

            if isinstance(e, (ReadTimeout, TimeoutException, TimeoutError)) and self._api_key:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/fileSearchStores?key={self._api_key}"
                    resp = httpx.post(url, json={"displayName": display_name}, timeout=settings.GEMINI_HTTP_TIMEOUT_S)
                    resp.raise_for_status()
                    data = resp.json()
                    name = data.get("name")
                    if not name:
                        raise ValueError("Missing store name in REST response")
                    return name
                except Exception:
                    # Fall through to original exception if REST also fails
                    pass
            raise

    # -------- Upload & Operations --------
    @_gemini_retry()
    def upload_file(
        self,
        store_name: str,
        file_path: str,
        *,
        display_name: Optional[str] = None,
        custom_metadata: Optional[List[Dict[str, Union[str, float, int]]]] = None,
        chunking_config: Optional[Dict] = None,
    ) -> UploadResult:
        start = time.perf_counter()
        try:
            op = self.client.file_search_stores.upload_to_file_search_store(
                file=file_path,
                file_search_store_name=store_name,
                config={
                    **({"display_name": display_name} if display_name else {}),
                    **({"custom_metadata": custom_metadata} if custom_metadata else {}),
                    **({"chunking_config": chunking_config} if chunking_config else {}),
                },
            )
            op_name = _get_response_name(op, context="file upload")
            file_id = _extract_uploaded_file_id(op)
            gemini_calls_total.labels("upload", "ok").inc()
            return UploadResult(operation_name=op_name, file_id=file_id)
        except errors.APIError as e:
            gemini_calls_total.labels("upload", "error").inc()
            logging.error(
                "Upload failed for store",
                extra={
                    "store": store_name,
                    "file": file_path,
                    "error_type": type(e).__name__,
                    "error_code": getattr(e, "code", None),
                },
            )
            raise
        except ValueError as e:
            gemini_calls_total.labels("upload", "error").inc()
            logging.error(
                "Upload response missing operation name",
                extra={"store": store_name, "file": file_path, "error_type": type(e).__name__},
            )
            raise
        finally:
            gemini_latency.labels("upload").observe(time.perf_counter() - start)

    @_gemini_retry()
    def delete_store(self, store_name: str) -> None:
        """Best-effort deletion for Gemini File Search stores."""
        if not store_name:
            return
        try:
            delete_fn = getattr(self.client.file_search_stores, "delete", None)
            if callable(delete_fn):
                delete_fn(name=store_name)
                return
        except errors.APIError as exc:
            # Treat 404 as success (already removed)
            if getattr(exc, "code", None) == 404:
                logging.info("Store already deleted remotely", extra={"store": store_name})
                return
            raise

        # Fallback to REST delete if SDK delete is missing (seen in constrained envs)
        if self._api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/{store_name}?key={self._api_key}"
            try:
                resp = httpx.delete(url, timeout=settings.GEMINI_HTTP_TIMEOUT_S)
                if resp.status_code not in (200, 204, 404):
                    logging.warning(
                        "Gemini REST delete returned unexpected status",
                        extra={"store": store_name, "status": resp.status_code},
                    )
            except httpx.HTTPError as exc:
                logging.warning(
                    "Gemini REST delete failed",
                    extra={"store": store_name, "error_type": type(exc).__name__},
                )
            return

    def delete_document_from_store(
        self, store_name: str, document_id: int, filename: str | None = None, file_id: str | None = None
    ) -> None:
        """Delete a Gemini file associated with a document; treat 404 as success."""
        if not file_id:
            logging.info(
                "No gemini_file_id recorded; skipping remote delete",
                extra={"store": store_name, "document_id": document_id, "filename": filename},
            )
            return
        try:
            delete_fn = getattr(self.client.files, "delete", None)
            if callable(delete_fn):
                delete_fn(name=file_id)
                return
            logging.warning(
                "Gemini client missing files.delete handler",
                extra={"store": store_name, "document_id": document_id, "file_id": file_id},
            )
        except errors.APIError as exc:
            if getattr(exc, "code", None) == 404:
                logging.info(
                    "Gemini file already deleted",
                    extra={"store": store_name, "document_id": document_id, "file_id": file_id},
                )
                return
            raise
        except Exception as exc:
            logging.warning(
                "Gemini delete_file failed",
                extra={"store": store_name, "document_id": document_id, "file_id": file_id, "error": str(exc)},
            )
            raise

    def op_status(self, op_name: str | dict) -> dict[str, Any]:
        op_name_str = _get_response_name(op_name, context="operation status request")

        # Prefer REST when we have an API key; SDK expects an operation object, not a raw string.
        if self._api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/{op_name_str}?key={self._api_key}"
            try:
                resp = httpx.get(url, timeout=settings.GEMINI_HTTP_TIMEOUT_S)
                resp.raise_for_status()
                data = resp.json() if resp.content else {}
                return _normalize_operation_result(data, name=op_name_str, context="operation status response")
            except httpx.HTTPError as exc:
                logger.warning(
                    "REST op_status failed, falling back to SDK",
                    extra={"op_name": op_name_str, "error": str(exc)},
                )

        try:
            op_wrapper = SimpleNamespace(name=op_name_str)
            op = self.client.operations.get(op_wrapper)
            return _normalize_operation_result(op, name=op_name_str, context="operation status response")
        except (TypeError, AttributeError) as exc:
            logger.error(
                "SDK operations.get failed",
                extra={"op_name": op_name_str, "error": str(exc)},
            )
            raise ValueError(f"Failed to get operation status for {op_name_str}: {exc}") from exc

    # -------- Query (sync & stream) --------
    def _file_search_tool(self, store_names: Sequence[str], metadata_filter: Optional[Any]) -> types.Tool:
        return types.Tool(
            file_search=types.FileSearch(
                file_search_store_names=list(store_names),
                metadata_filter=metadata_filter,
            )
        )

    @staticmethod
    def _prepend_system(contents: Any, system: str) -> Any:
        system_msg = {"role": "user", "parts": [{"text": system}]}
        if isinstance(contents, list):
            return [system_msg, *contents]
        if isinstance(contents, str):
            user_msg = {"role": "user", "parts": [{"text": contents}]}
            return [system_msg, user_msg]
        return [system_msg, {"role": "user", "parts": [{"text": str(contents)}]}]

    @_gemini_retry()
    def ask(
        self,
        *,
        contents: Any,
        store_names: Sequence[str],
        metadata_filter: Optional[Any],
        model: str,
        system: str | None = None,
    ) -> Any:
        start = time.perf_counter()
        try:
            tool = self._file_search_tool(store_names, metadata_filter)
            try:
                config = (
                    types.GenerateContentConfig(tools=[tool], system_instruction=system)
                    if system
                    else types.GenerateContentConfig(tools=[tool])
                )
                resp = self.client.models.generate_content(model=model, contents=contents, config=config)
            except TypeError:
                # Older clients may not accept system_instruction; fall back to embedding as the first content turn.
                config = types.GenerateContentConfig(tools=[tool])
                resp = self.client.models.generate_content(
                    model=model,
                    contents=self._prepend_system(contents, system) if system else contents,
                    config=config,
                )
            gemini_calls_total.labels("generate", "ok").inc()
            return resp
        except errors.APIError:
            gemini_calls_total.labels("generate", "error").inc()
            raise
        finally:
            gemini_latency.labels("generate").observe(time.perf_counter() - start)

    def ask_stream(
        self,
        *,
        contents: Any,
        store_names: Sequence[str],
        metadata_filter: Optional[Any],
        model: str,
        system: str | None = None,
    ) -> Generator:
        # Streaming initial connection may fail; wrap connect phase with retry
        tool = self._file_search_tool(store_names, metadata_filter)
        start = time.perf_counter()
        try:
            try:
                config = (
                    types.GenerateContentConfig(tools=[tool], system_instruction=system)
                    if system
                    else types.GenerateContentConfig(tools=[tool])
                )
                stream_iter = self.client.models.generate_content_stream(model=model, contents=contents, config=config)
            except TypeError:
                config = types.GenerateContentConfig(tools=[tool])
                stream_iter = self.client.models.generate_content_stream(
                    model=model,
                    contents=self._prepend_system(contents, system) if system else contents,
                    config=config,
                )
            gemini_calls_total.labels("generate_stream", "ok").inc()
            for chunk in stream_iter:
                yield chunk
        except errors.APIError:
            gemini_calls_total.labels("generate_stream", "error").inc()
            raise
        finally:
            gemini_latency.labels("generate_stream").observe(time.perf_counter() - start)

    # -------- Citations --------
    @staticmethod
    def extract_citations_from_response(response: Any) -> List[dict[str, Any]]:
        out: List[dict[str, Any]] = []
        try:
            cand = response.candidates[0]
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                return out
            chunks = list(getattr(gm, "grounding_chunks", []) or [])
            for i, ch in enumerate(chunks):
                rc = getattr(ch, "retrieved_context", None)
                if rc:
                    out.append(
                        {
                            "index": i,
                            "source_type": "retrieved_context",
                            "uri": getattr(rc, "uri", None),
                            "title": getattr(rc, "title", None),
                            "snippet": getattr(rc, "text", None),
                            "store": getattr(rc, "file_search_store", None),
                        }
                    )
                    continue
                web = getattr(ch, "web", None)
                if web:
                    out.append(
                        {
                            "index": i,
                            "source_type": "web",
                            "uri": getattr(web, "uri", None),
                            "title": getattr(web, "title", None),
                            "snippet": None,
                            "store": None,
                        }
                    )
            return out
        except (AttributeError, KeyError, IndexError, TypeError) as e:
            logging.warning(
                f"Failed to extract citations: {e}",
                extra={"response_type": type(response).__name__, "has_candidates": hasattr(response, "candidates")},
            )
            return out

    @staticmethod
    def new_stream_ids() -> tuple[str, str]:
        return str(uuid.uuid4()), str(uuid.uuid4())


class MockGeminiRag(GeminiRag):
    def __init__(self) -> None:
        self.is_mock = True
        self._store_counter = 0

    def list_stores(self) -> List[types.FileSearchStore]:
        return []

    def create_store(self, display_name: str) -> str:
        self._store_counter += 1
        return f"fileSearchStores/mock-{uuid.uuid4().hex}"

    def upload_file(
        self,
        store_name: str,
        file_path: str,
        *,
        display_name: Optional[str] = None,
        custom_metadata: Optional[List[Dict[str, Union[str, float, int]]]] = None,
        chunking_config: Optional[Dict] = None,
    ) -> UploadResult:
        start = time.perf_counter()
        try:
            op_name = f"operations/mock-{uuid.uuid4().hex}"
            gemini_calls_total.labels("upload", "ok").inc()
            return UploadResult(operation_name=op_name, file_id=f"files/mock-{uuid.uuid4().hex}")
        finally:
            gemini_latency.labels("upload").observe(time.perf_counter() - start)

    def op_status(self, op_name: str | dict) -> dict[str, Any]:
        op_name_str = _get_response_name(op_name, context="mock operation status request")
        return {
            "name": op_name_str,
            "done": True,
            "metadata": {},
            "error": None,
        }

    @staticmethod
    def _contents_to_text(contents: Any) -> str:
        if isinstance(contents, str):
            return contents
        if isinstance(contents, list):
            for item in reversed(contents):
                if isinstance(item, str) and item.strip():
                    return item.strip()
                if isinstance(item, dict):
                    parts = item.get("parts")
                    if isinstance(parts, list) and parts and isinstance(parts[0], dict):
                        text = parts[0].get("text")
                        if isinstance(text, str) and text.strip():
                            return text.strip()
        return str(contents)

    def ask(
        self,
        *,
        contents: Any,
        store_names: Sequence[str],
        metadata_filter: Optional[str],
        model: str,
        system: str | None = None,
    ) -> Any:
        start = time.perf_counter()
        try:
            resp = self._mock_response(self._contents_to_text(contents), store_names)
            gemini_calls_total.labels("generate", "ok").inc()
            return resp
        finally:
            gemini_latency.labels("generate").observe(time.perf_counter() - start)

    def ask_stream(
        self,
        *,
        contents: Any,
        store_names: Sequence[str],
        metadata_filter: Optional[str],
        model: str,
        system: str | None = None,
    ) -> Generator:
        start = time.perf_counter()
        try:
            text = self._contents_to_text(contents)
            resp = self._mock_response(text, store_names)
            gemini_calls_total.labels("generate_stream", "ok").inc()
            yield SimpleNamespace(
                text=f"[mock-mode] {text or 'response'}",
                candidates=None,
                usage_metadata=SimpleNamespace(prompt_token_count=0, candidates_token_count=0),
            )
            yield resp
        finally:
            gemini_latency.labels("generate_stream").observe(time.perf_counter() - start)

    def delete_store(self, store_name: str) -> None:
        logging.info(f"[mock] delete_store called for {store_name}")

    def delete_document_from_store(
        self, store_name: str, document_id: int, filename: str | None = None, file_id: str | None = None
    ) -> None:
        logging.info(f"[mock] delete_document called for document {document_id} in {store_name} (file_id={file_id})")

    def _mock_response(self, question: str, store_names: Sequence[str]) -> Any:
        snippet = question[:128] if question else "Mock response"
        usage = SimpleNamespace(prompt_token_count=0, candidates_token_count=0)
        retrieved_context = SimpleNamespace(
            uri="mock://document",
            title="Mock Document",
            text=f"Mock snippet: {snippet}",
            file_search_store=store_names[0] if store_names else "store/mock",
        )
        grounding_chunk = SimpleNamespace(retrieved_context=retrieved_context, web=None)
        candidate = SimpleNamespace(
            grounding_metadata=SimpleNamespace(grounding_chunks=[grounding_chunk]),
            usage_metadata=usage,
        )
        return SimpleNamespace(text=None, candidates=[candidate], usage_metadata=usage)


def get_rag_client() -> GeminiRag:
    """Return the appropriate Gemini client (real or mock) for the current environment."""
    if settings.GEMINI_MOCK_MODE and settings.ENVIRONMENT in {"development", "test"}:
        return MockGeminiRag()
    return GeminiRag(api_key=settings.GEMINI_API_KEY)
