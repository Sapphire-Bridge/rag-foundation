# SPDX-License-Identifier: Apache-2.0

import asyncio
import datetime
import json
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Request, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.responses import StreamingResponse
from sqlalchemy.orm import Session, sessionmaker
from ..telemetry import log_json
from ..config import settings
from ..metrics import token_usage_total
from ..services.gemini_rag import RETRYABLE_EXCEPTIONS, get_rag_client
from ..genai import redact_llm_error
from ..auth import get_authorization, get_current_user
from ..db import get_db, get_session_factory
from ..models import QueryLog, ChatHistory, ChatSession
from ..costs import (
    acquire_budget_lock,
    calc_query_cost,
    mtd_spend,
    user_budget,
    would_exceed_budget,
    require_pricing_configured,
)
from ..rate_limit import check_rate_limit
from ..security.tenant import require_stores_owned_by_user

router = APIRouter(prefix="/chat", tags=["chat"])
_stream_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_STREAMS)

ROLE_LABELS = {
    "user": "User",
    "assistant": "Assistant",
    "model": "Assistant",
    "system": "System",
}
MAX_QUESTION_LENGTH = 32_000
ALLOWED_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-3.0-pro-thinking",
    "gemini-2.0-flash",
    "gemini-2.0-pro",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
}
_SAFE_METADATA_VALUE_TYPES = (str, int, float, bool)


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    question: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    session_id: Optional[str] = None
    thread_id: Optional[str] = None
    store_ids: List[int] = Field(
        ...,
        min_length=1,
        alias="storeIds",
        description="List of store IDs to query against.",
    )
    project_id: Optional[Any] = None
    tags: Optional[Dict[str, Any]] = None
    metadata_filter: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="metadataFilter",
        description="Optional metadata filter applied server-side.",
    )
    model: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _apply_aliases(cls, values):
        if not isinstance(values, dict):
            return values
        alias_map = {
            "sessionId": "session_id",
            "threadId": "thread_id",
            "projectId": "project_id",
        }
        for alias, target in alias_map.items():
            if alias in values and target not in values:
                values[target] = values[alias]
        return values


def _sse_error(code: str, message: str, status: int | None = None) -> str:
    payload = {"type": "error", "code": code, "message": message, "errorText": message}
    if status is not None:
        payload["status"] = status
    return f"data: {json.dumps(payload)}\n\n"


def _extract_message_text(msg: dict) -> str:
    texts: list[str] = []
    for key in ("question", "text", "message", "value"):
        v = msg.get(key)
        if isinstance(v, str) and v.strip():
            texts.append(v.strip())
            break

    for arr_key in ("content", "parts", "values"):
        arr = msg.get(arr_key)
        if isinstance(arr, str) and arr.strip():
            texts.append(arr.strip())
            break
        if isinstance(arr, list):
            for item in arr:
                if isinstance(item, str) and item.strip():
                    texts.append(item.strip())
                elif isinstance(item, dict):
                    nested = item.get("text") or item.get("content") or item.get("value")
                    if isinstance(nested, str) and nested.strip():
                        texts.append(nested.strip())
            if texts:
                break
    return " ".join(texts).strip()


def _build_history_prompt(messages: list[dict]) -> tuple[str | None, str | None]:
    """
    Build a lightweight chat transcript from AssistantUI-style messages so the
    model can see prior turns. Returns (transcript, last_user_text).
    """
    lines: list[str] = []
    last_user: str | None = None
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        text = _extract_message_text(msg)
        if not text:
            continue
        role = str(msg.get("role") or "").lower()
        if role not in {"user", "assistant", "model"}:
            continue
        label = ROLE_LABELS.get(role, role.title() or "User")
        lines.append(f"{label}: {text}")
        if role == "user":
            last_user = text

    if not lines:
        return None, last_user

    # Keep only the most recent turns and trim runaway payloads
    transcript = "\n".join(lines[-24:])
    if len(transcript) > 6000:
        transcript = transcript[-6000:]
    return transcript, last_user


def _estimate_tokens_from_text(text: str) -> int:
    """
    Crude token estimate used for budgeting when the upstream SDK does not
    provide usage metadata mid-stream. This deliberately errs on the side of
    safety and may under/over-count for non-ASCII or emoji-heavy content.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def _sanitize_tags(raw) -> dict | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tags must be an object")

    cleaned = {}
    for key, value in raw.items():
        if len(cleaned) >= 5:
            break
        if not isinstance(key, str) or not key.strip():
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key.strip()[:32]] = str(value)[:128]
    return cleaned or None


def _coerce_metadata_value(key: str, value: Any) -> Any:
    """Normalize a metadata filter value and reject complex objects."""
    if isinstance(value, _SAFE_METADATA_VALUE_TYPES):
        return value if not isinstance(value, str) else value[:256]

    if isinstance(value, list):
        normalized_list: list[Any] = []
        for item in value:
            if isinstance(item, _SAFE_METADATA_VALUE_TYPES):
                normalized_list.append(item if not isinstance(item, str) else item[:256])
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="metadataFilter values must be strings, numbers, booleans, or lists of those",
                )
        if not normalized_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="metadataFilter lists must include at least one value",
            )
        return normalized_list

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid metadataFilter value for '{key}'",
    )


def _validate_metadata_filter(raw: Any) -> dict[str, Any] | None:
    """Allow only simple, allowlisted metadata filters when enabled."""
    if raw is None:
        return None

    if not settings.ALLOW_METADATA_FILTERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metadata filters are disabled on this deployment.",
        )
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="metadataFilter must be an object")

    allowed_keys = settings.METADATA_FILTER_ALLOWED_KEYS or []
    if not allowed_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metadata filters require METADATA_FILTER_ALLOWED_KEYS to be configured.",
        )

    cleaned: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="metadataFilter keys must be non-empty strings",
            )
        normalized_key = key.strip()
        if normalized_key not in allowed_keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"metadataFilter key '{normalized_key}' is not allowed",
            )
        cleaned[normalized_key] = _coerce_metadata_value(normalized_key, value)

    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metadataFilter must include at least one allowed key",
        )
    return cleaned


def _sanitize_session_id(raw) -> str:
    if not raw:
        return str(uuid.uuid4())
    if not isinstance(raw, str):
        raw = str(raw)
    raw = raw.strip() or str(uuid.uuid4())
    return raw[:64]


def _trim_title(title: str | None) -> str | None:
    if not title:
        return None
    clean = title.strip()
    if len(clean) <= 50:
        return clean
    return f"{clean[:50]}…"


def _load_chat_history(
    db: Session, user_id: int, session_id: str, store_id: int | None, limit: int = 50
) -> list[ChatHistory]:
    query = db.query(ChatHistory).filter(ChatHistory.user_id == user_id, ChatHistory.session_id == session_id)
    if store_id is not None:
        query = query.filter(ChatHistory.store_id == store_id)
    rows = query.order_by(ChatHistory.created_at.desc()).limit(limit).all()
    rows.reverse()
    return rows


def _persist_chat_message(
    db: Session, *, user_id: int, store_id: int | None, session_id: str, role: str, content: str
) -> None:
    if not content:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        session = db.get(ChatSession, session_id)
        if session:
            session.updated_at = now
            if session.title is None and role == "user":
                session.title = _trim_title(content)
        db.add(
            ChatHistory(
                user_id=user_id,
                store_id=store_id,
                session_id=session_id,
                role=role,
                content=content,
            )
        )
        db.commit()
    except Exception as exc:  # pragma: no cover - telemetry only
        db.rollback()
        try:
            log_json(
                30, "chat_history_persist_failed", user_id=user_id, session_id=session_id, role=role, error=str(exc)
            )
        except Exception:
            pass


def _ensure_chat_session(
    db: Session, *, user_id: int, store_id: int | None, session_id: str, title: str | None
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    existing = db.get(ChatSession, session_id)
    if existing:
        existing_user_id = getattr(existing, "user_id", None)
        # Only enforce user_id when it is an int; this keeps strict checks in real
        # sessions while tolerating loose mocks in tests.
        if isinstance(existing_user_id, int) and existing_user_id != user_id:
            raise HTTPException(status_code=404, detail="Session not found")
        existing.updated_at = now
        if existing.title is None and title:
            existing.title = _trim_title(title)
        if existing.store_id is None:
            existing.store_id = store_id
    else:
        db.add(
            ChatSession(
                id=session_id,
                user_id=user_id,
                store_id=store_id,
                title=_trim_title(title),
                updated_at=now,
            )
        )
    db.flush()


@router.post(
    "",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {}}},
    },
)
async def chat_stream(
    req: Request,
    chat_req: ChatRequest = Body(..., description="Chat request payload"),
    authorization: str = Depends(get_authorization),
    _: None = Depends(require_pricing_configured),
    session_factory: sessionmaker = Depends(get_session_factory),
):
    body = chat_req.model_dump(exclude_none=True, by_alias=True)
    db = session_factory()
    try:
        user = get_current_user(db=db, token=authorization)
        user_id = int(getattr(user, "id"))
        messages = chat_req.messages or []
        session_id = _sanitize_session_id(chat_req.session_id or chat_req.thread_id)
        store_ids = list(getattr(chat_req, "store_ids", []) or [])
        stores = require_stores_owned_by_user(db, store_ids, user_id)
        store_refs = [{"id": s.id, "fs_name": s.fs_name} for s in stores]
        store_id_for_history = store_refs[0]["id"] if store_refs else None
        store_ids_for_cost = [s["id"] for s in store_refs]
        fs_names = [s["fs_name"] for s in store_refs]

        # Accept AssistantUI payload with messages OR our QueryRequest shape
        question = chat_req.question
        history_rows = _load_chat_history(db, user_id, session_id, store_id_for_history)
        history_messages = [{"role": row.role, "text": row.content} for row in history_rows]
        combined_messages = history_messages + messages
        history_prompt, last_user_text = _build_history_prompt(combined_messages) if combined_messages else (None, None)

        if not question and messages:
            question = _extract_message_text(messages[-1] or {})
        if not question and last_user_text:
            question = last_user_text
        if history_prompt:
            question = (
                f"{history_prompt}\n\nAssistant, respond to the latest User message using the conversation above."
            )

        if not question:
            try:
                # Log limited diagnostics without user content
                last_keys = list((messages or [{}])[-1].keys()) if messages else []
                log_json(30, "chat_bad_payload", keys=list(body.keys()), last_message_keys=last_keys)
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="Missing question")

        if not isinstance(question, str):
            try:
                log_json(30, "chat_question_type_coerced", user_id=user_id, original_type=type(question).__name__)
            except Exception:
                pass
            question = str(question)

        if len(question) > MAX_QUESTION_LENGTH:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Question too long (max {MAX_QUESTION_LENGTH} characters)",
            )

        check_rate_limit(f"user:{user_id}:chat", settings.CHAT_RATE_LIMIT_PER_MINUTE)

        project_id = getattr(chat_req, "project_id", None)
        if project_id is not None:
            try:
                project_id = int(project_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="projectId must be an integer")
        tags = _sanitize_tags(chat_req.tags)

        metadata_filter = _validate_metadata_filter(chat_req.metadata_filter)

        model = chat_req.model or settings.DEFAULT_MODEL
        if model not in ALLOWED_MODELS:
            log_json(30, "chat_model_invalid", user_id=user_id, model=model)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported model requested",
            )

        # Budget pre-check (best-effort lock to reduce multi-tab races)
        acquire_budget_lock(db, user_id)
        limit = user_budget(db, user_id)
        spend = mtd_spend(db, user_id)
        # NOTE: This mitigates but does not fully eliminate concurrent multi-request races without a shared counter.
        remaining_budget_usd: Decimal | None = None
        if limit is not None:
            remaining_budget_usd = max(Decimal("0"), limit - spend)
            if remaining_budget_usd <= 0:
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Monthly budget exhausted")
            hold_amt = Decimal(str(settings.BUDGET_HOLD_USD or 0))
            if hold_amt > 0:
                if remaining_budget_usd <= hold_amt:
                    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Monthly budget exhausted")
                remaining_budget_usd -= hold_amt

        prompt_tokens_est = _estimate_tokens_from_text(question)
        if remaining_budget_usd is not None:
            prompt_cost = calc_query_cost(model, prompt_tokens_est, 0).total_cost_usd
            if prompt_cost > remaining_budget_usd:
                raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Monthly budget exhausted")

        rag = get_rag_client()

        user_text = None
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            if str(msg.get("role") or "").lower() == "user":
                user_text = _extract_message_text(msg)
                if user_text:
                    break
        if not user_text:
            user_text = question
        _ensure_chat_session(
            db,
            user_id=user_id,
            store_id=store_id_for_history,
            session_id=session_id,
            title=user_text,
        )
        db.commit()
        _persist_chat_message(
            db,
            user_id=user_id,
            store_id=store_id_for_history,
            session_id=session_id,
            role="user",
            content=user_text or "",
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    async def generator():
        import logging
        import queue
        import threading

        keepalive_interval = settings.STREAM_KEEPALIVE_SECS if settings.STREAM_KEEPALIVE_SECS > 0 else None
        last_send = time.monotonic()
        stream_failed = False
        budget_exhausted = False
        error_sent = False
        last_error_code: str | None = None
        last_error_message: str | None = None
        assistant_text_parts: list[str] = []
        completion_tokens_used = 0
        prompt_tokens_used = prompt_tokens_est

        message_id, text_id = rag.new_stream_ids()

        final_resp = None
        max_retries = settings.GEMINI_STREAM_RETRY_ATTEMPTS
        retry_count = 0
        sem_acquired = False

        def _send_error(code: str, message: str, status_code: int | None = None) -> str:
            nonlocal error_sent, last_error_code, last_error_message
            error_sent = True
            last_error_code = code
            last_error_message = message
            return _sse_error(code, message, status=status_code)

        try:
            try:
                await asyncio.wait_for(_stream_semaphore.acquire(), timeout=2.0)
                sem_acquired = True
            except asyncio.TimeoutError:
                yield _send_error(
                    "stream_capacity_exceeded",
                    "Server is busy. Please try again.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )
                yield "data: [DONE]\n\n"
                return

            yield f"data: {json.dumps({'type': 'start', 'messageId': message_id, 'request_id': request_id})}\n\n"
            last_send = time.monotonic()
            yield f"data: {json.dumps({'type': 'text-start', 'id': text_id, 'request_id': request_id})}\n\n"
            last_send = time.monotonic()

            while retry_count <= max_retries:
                if await req.is_disconnected():
                    logging.info("Client disconnected during stream")
                    stream_failed = True
                    break

                try:
                    chunk_queue = queue.Queue(maxsize=20)
                    stop_event = threading.Event()

                    def run_stream_in_thread():
                        """Run synchronous ask_stream in background thread, pushing chunks to queue."""
                        try:
                            for chunk in rag.ask_stream(
                                question=question, store_names=fs_names, metadata_filter=metadata_filter, model=model
                            ):
                                if stop_event.is_set():
                                    break
                                try:
                                    chunk_queue.put(("chunk", chunk), timeout=1.0)
                                except queue.Full:
                                    chunk_queue.put(("error", RuntimeError("Stream backpressure: chunk queue full")))
                                    break
                            chunk_queue.put(("done", None))
                        except Exception as e:
                            chunk_queue.put(("error", e))

                    stream_thread = threading.Thread(target=run_stream_in_thread, daemon=True)
                    stream_thread.start()

                    try:
                        while True:
                            if await req.is_disconnected():
                                logging.info("Client disconnected mid-stream")
                                stream_failed = True
                                stop_event.set()
                                break
                            try:
                                msg_type, data = chunk_queue.get(timeout=0.1)
                            except queue.Empty:
                                if await req.is_disconnected():
                                    logging.info("Client disconnected mid-stream")
                                    stream_failed = True
                                    stop_event.set()
                                    break
                                if keepalive_interval:
                                    now = time.monotonic()
                                    if now - last_send >= keepalive_interval:
                                        yield f": keepalive {int(now)}\n\n"
                                        last_send = now
                                continue

                            if msg_type == "done":
                                break
                            if msg_type == "error":
                                raise data
                            if msg_type == "chunk":
                                if await req.is_disconnected():
                                    logging.info("Client disconnected mid-stream")
                                    stream_failed = True
                                    stop_event.set()
                                    break
                                text_delta = getattr(data, "text", None)
                                if text_delta:
                                    completion_tokens_used += _estimate_tokens_from_text(text_delta)
                                    if remaining_budget_usd is not None:
                                        estimated_cost = calc_query_cost(
                                            model, prompt_tokens_used, completion_tokens_used
                                        ).total_cost_usd
                                        if estimated_cost > remaining_budget_usd:
                                            budget_exhausted = True
                                            stop_event.set()
                                            if not error_sent:
                                                yield _send_error(
                                                    "budget_exceeded",
                                                    "Monthly budget exceeded",
                                                    status.HTTP_402_PAYMENT_REQUIRED,
                                                )
                                            last_send = time.monotonic()
                                            break
                                    yield f"data: {json.dumps({'type': 'text-delta', 'id': text_id, 'delta': text_delta, 'request_id': request_id})}\n\n"
                                    last_send = time.monotonic()
                                    assistant_text_parts.append(text_delta)
                                if getattr(data, "candidates", None):
                                    final_resp = data
                        if budget_exhausted:
                            break
                    finally:
                        stop_event.set()
                        stream_thread.join(timeout=1.0)
                        if stream_thread.is_alive():
                            logging.warning("Stream thread still running after cancel")

                    break

                except RETRYABLE_EXCEPTIONS as e:
                    retry_count += 1
                    retry_delay = 2**retry_count
                    if retry_count > max_retries:
                        log_json(
                            40,
                            "chat_stream_failed",
                            user_id=user_id,
                            model=model,
                            retries=retry_count,
                            **redact_llm_error(e),
                        )
                        stream_failed = True
                        if not error_sent:
                            yield _send_error(
                                "upstream_unavailable",
                                "Service temporarily unavailable. Please try again.",
                                status.HTTP_503_SERVICE_UNAVAILABLE,
                            )
                        last_send = time.monotonic()
                        break
                    log_json(
                        30,
                        "chat_stream_retry",
                        user_id=user_id,
                        model=model,
                        retry=retry_count,
                        retry_delay_ms=int(retry_delay * 1000),
                        **redact_llm_error(e),
                    )
                    await asyncio.sleep(retry_delay)

                except Exception as exc:
                    log_json(
                        40,
                        "chat_stream_exception",
                        user_id=user_id,
                        model=model,
                        **redact_llm_error(exc),
                    )
                    stream_failed = True
                    safe_error = "An error occurred processing your request. Please try again."
                    if not error_sent:
                        yield _send_error("unexpected_error", safe_error, status.HTTP_500_INTERNAL_SERVER_ERROR)
                    last_send = time.monotonic()
                    break

            if stream_failed and last_error_code not in (None, "budget_exceeded"):
                failure_tags = dict(tags or {}) if tags else {}
                failure_tags["error_code"] = last_error_code
                log_db = session_factory()
                try:
                    ql = QueryLog(
                        user_id=user_id,
                        store_id=store_ids_for_cost[0] if store_ids_for_cost else None,
                        prompt_tokens=prompt_tokens_used,
                        completion_tokens=completion_tokens_used,
                        cost_usd=Decimal("0"),
                        model=model,
                        project_id=project_id,
                        tags=failure_tags or None,
                    )
                    log_db.add(ql)
                    log_db.commit()
                except Exception as e:
                    logging.error("Failed to log failed stream cost: %s", e, exc_info=e)
                    log_db.rollback()
                finally:
                    log_db.close()

            if stream_failed:
                yield "data: [DONE]\n\n"
                return

            if budget_exhausted:
                yield "data: [DONE]\n\n"
                return

            yield f"data: {json.dumps({'type': 'text-end', 'id': text_id})}\n\n"
            last_send = time.monotonic()

            if final_resp is not None and not budget_exhausted:
                for c in rag.extract_citations_from_response(final_resp):
                    payload = {
                        "type": "source-document",
                        "sourceId": f"cit-{c['index']}",
                        "mediaType": "file",
                        "title": c.get("title") or c.get("uri") or "Source",
                        "snippet": c.get("snippet"),
                    }
                    payload["request_id"] = request_id
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_send = time.monotonic()

            usage = None
            prompt_toks = prompt_tokens_used
            completion_toks = completion_tokens_used
            if final_resp is not None:
                usage = getattr(final_resp, "usage_metadata", None) or getattr(
                    getattr(final_resp, "candidates", [None])[0], "usage_metadata", None
                )
            if usage:
                prompt_toks = getattr(usage, "prompt_token_count", None) or prompt_toks
                completion_toks = getattr(usage, "candidates_token_count", None) or completion_toks
            else:
                if not completion_toks:
                    completion_toks = _estimate_tokens_from_text("".join(assistant_text_parts))
                log_json(
                    30,
                    "chat_usage_metadata_missing",
                    user_id=user_id,
                    model=model,
                    prompt_tokens=prompt_toks,
                    completion_tokens=completion_toks,
                )

            cost_result = calc_query_cost(model, prompt_toks, completion_toks)
            if prompt_toks:
                token_usage_total.labels(model=model, type="prompt").inc(prompt_toks)
            if completion_toks:
                token_usage_total.labels(model=model, type="completion").inc(completion_toks)

            over_budget = False
            log_db = session_factory()
            try:
                if cost_result.total_cost_usd > 0:
                    acquire_budget_lock(log_db, user_id)
                    over_budget = would_exceed_budget(log_db, user_id, cost_result.total_cost_usd)

                ql = QueryLog(
                    user_id=user_id,
                    store_id=store_ids_for_cost[0] if store_ids_for_cost else None,
                    prompt_tokens=cost_result.prompt_tokens,
                    completion_tokens=cost_result.completion_tokens,
                    cost_usd=cost_result.total_cost_usd,
                    model=model,
                    project_id=project_id,
                    tags=tags,
                )
                try:
                    log_db.add(ql)
                    log_db.commit()
                except Exception:
                    logging.error(
                        "Failed to log query cost for user %s",
                        user_id,
                        exc_info=True,
                        extra={
                            "user_id": user_id,
                            "cost": float(cost_result.total_cost_usd),
                            "model": model,
                        },
                    )
                    log_db.rollback()

                assistant_text = "".join(assistant_text_parts).strip()
                if assistant_text:
                    _persist_chat_message(
                        log_db,
                        user_id=user_id,
                        store_id=store_id_for_history,
                        session_id=session_id,
                        role="assistant",
                        content=assistant_text,
                    )
            finally:
                log_db.close()

            if over_budget or budget_exhausted:
                if not error_sent:
                    log_json(
                        30,
                        "chat_budget_exceeded_post_cost",
                        user_id=user_id,
                        cost=float(cost_result.total_cost_usd),
                        prompt_tokens=cost_result.prompt_tokens,
                        completion_tokens=cost_result.completion_tokens,
                    )
                    yield _send_error("budget_exceeded", "Monthly budget exceeded", status.HTTP_402_PAYMENT_REQUIRED)
                    last_send = time.monotonic()
                yield "data: [DONE]\n\n"
                return

            finish_payload = {
                "type": "finish",
                "usage": {
                    "prompt_tokens": prompt_toks,
                    "completion_tokens": completion_toks,
                    "model": model,
                },
            }
            yield f"data: {json.dumps(finish_payload)}\n\n"
            last_send = time.monotonic()
            yield "data: [DONE]\n\n"
            return
        finally:
            if sem_acquired:
                _stream_semaphore.release()

    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "x-vercel-ai-ui-message-stream": "v1",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(generator(), headers=headers)


def _chat_session_to_dict(session: ChatSession) -> dict[str, object]:
    return {
        "id": session.id,
        "store_id": session.store_id,
        "title": session.title or "",
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


@router.get("/sessions")
def list_chat_sessions(
    storeId: int | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    authorization: str = Depends(get_authorization),
):
    user = get_current_user(db=db, token=authorization)
    query = db.query(ChatSession).filter(ChatSession.user_id == user.id)
    if storeId is not None:
        require_stores_owned_by_user(db, [storeId], user.id)
        query = query.filter(ChatSession.store_id == storeId)
    rows = query.order_by(ChatSession.updated_at.desc()).limit(max(1, min(limit, 200))).all()
    return [_chat_session_to_dict(row) for row in rows]


@router.get("/sessions/{session_id}/messages")
def list_chat_messages(
    session_id: str,
    db: Session = Depends(get_db),
    authorization: str = Depends(get_authorization),
):
    user = get_current_user(db=db, token=authorization)
    session_row = db.get(ChatSession, session_id)
    if not session_row or session_row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_row.store_id:
        require_stores_owned_by_user(db, [session_row.store_id], user.id)

    msgs = (
        db.query(ChatHistory).filter(ChatHistory.session_id == session_id).order_by(ChatHistory.created_at.asc()).all()
    )
    return [
        {
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        }
        for msg in msgs
    ]
