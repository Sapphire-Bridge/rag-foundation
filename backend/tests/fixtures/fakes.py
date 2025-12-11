"""
Fake implementations for external dependencies.

Design principles:
- Same public interface as production
- Deterministic (no randomness, no real I/O)
- Inspectable (call logs, configurable responses)
"""

from collections import defaultdict
from dataclasses import dataclass, field


class FakeRedis:
    """
    In-memory Redis fake.

    Supports:
    - setex/get/exists (revocation)
    - incr/expire (rate limiting)
    - Pipeline (atomic ops)

    TTL handling:
    - Expiry timestamps are stored but only checked against real time
    - Use frozen_time fixture to control expiry behavior
    """

    def __init__(self):
        self._data: dict[str, str] = {}
        self._expiry: dict[str, float] = {}
        self._counters: dict[str, int] = defaultdict(int)
        self.call_log: list[tuple[str, tuple]] = []

    def _log(self, method: str, *args):
        self.call_log.append((method, args))

    def _is_expired(self, key: str) -> bool:
        import time

        if key not in self._expiry:
            return False
        return time.time() > self._expiry[key]

    def _cleanup_if_expired(self, key: str) -> bool:
        """Remove key if expired. Returns True if key was expired."""
        if self._is_expired(key):
            self._data.pop(key, None)
            self._expiry.pop(key, None)
            self._counters.pop(key, None)
            return True
        return False

    def setex(self, key: str, ttl: int, value: str) -> bool:
        import time

        self._log("setex", key, ttl, value)
        self._data[key] = value
        self._expiry[key] = time.time() + ttl
        return True

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        import time

        self._log("set", key, value, ex)
        self._data[key] = value
        if ex:
            self._expiry[key] = time.time() + ex
        return True

    def get(self, key: str) -> str | None:
        self._log("get", key)
        self._cleanup_if_expired(key)
        return self._data.get(key)

    def exists(self, key: str) -> bool:
        self._log("exists", key)
        self._cleanup_if_expired(key)
        return key in self._data

    def delete(self, *keys: str) -> int:
        self._log("delete", keys)
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                self._expiry.pop(key, None)
                count += 1
        return count

    def incr(self, key: str) -> int:
        self._log("incr", key)
        self._counters[key] += 1
        return self._counters[key]

    def expire(self, key: str, ttl: int) -> bool:
        import time

        self._log("expire", key, ttl)
        if key in self._data or key in self._counters:
            self._expiry[key] = time.time() + ttl
            return True
        return False

    def pipeline(self) -> "FakeRedisPipeline":
        return FakeRedisPipeline(self)

    def ping(self) -> bool:
        return True

    @classmethod
    def from_url(cls, url: str, **kwargs) -> "FakeRedis":
        return cls()

    # Test helpers
    def clear(self):
        self._data.clear()
        self._expiry.clear()
        self._counters.clear()
        self.call_log.clear()

    def get_counter(self, key: str) -> int:
        return self._counters.get(key, 0)

    def was_called(self, method: str) -> bool:
        return any(m == method for m, _ in self.call_log)


class FakeRedisPipeline:
    """Fake Redis pipeline."""

    def __init__(self, redis: FakeRedis):
        self._redis = redis
        self._commands: list[tuple[str, tuple, dict]] = []

    def incr(self, key: str) -> "FakeRedisPipeline":
        self._commands.append(("incr", (key,), {}))
        return self

    def expire(self, key: str, ttl: int) -> "FakeRedisPipeline":
        self._commands.append(("expire", (key, ttl), {}))
        return self

    def execute(self) -> list:
        results = []
        for method, args, kwargs in self._commands:
            func = getattr(self._redis, method)
            results.append(func(*args, **kwargs))
        self._commands.clear()
        return results

    def __enter__(self) -> "FakeRedisPipeline":
        return self

    def __exit__(self, *args):
        pass


@dataclass
class FakeUploadResult:
    """Result from FakeRAGClient.upload_file."""

    operation_name: str
    file_id: str


@dataclass
class FakeStreamChunk:
    """Fake stream chunk."""

    text: str
    candidates: list = field(default_factory=list)


@dataclass
class FakeRAGClient:
    """
    Fake Gemini RAG client.

    Configurable for:
    - upload_file success/failure
    - op_status states
    - ask_stream responses
    """

    is_mock: bool = True

    # State
    uploaded_files: list = field(default_factory=list)
    operations: dict = field(default_factory=dict)
    _upload_counter: int = 0
    _stream_counter: int = 0

    # Configurable behavior
    upload_should_fail: bool = False
    upload_error: str = "Simulated upload failure"
    stream_response: list = field(default_factory=lambda: ["Hello", " from", " assistant."])
    stream_should_fail: bool = False
    stream_error: str = "Simulated stream failure"

    def upload_file(self, store_name: str, path: str, display_name: str | None = None) -> FakeUploadResult:
        if self.upload_should_fail:
            raise RuntimeError(self.upload_error)

        self._upload_counter += 1
        op_name = f"operations/fake-op-{self._upload_counter}"
        file_id = f"files/fake-file-{self._upload_counter}"

        self.uploaded_files.append(
            {
                "store": store_name,
                "path": path,
                "display_name": display_name,
                "op_name": op_name,
                "file_id": file_id,
            }
        )

        self.operations[op_name] = {"done": True, "error": None}

        return FakeUploadResult(operation_name=op_name, file_id=file_id)

    def op_status(self, op_name: str) -> dict:
        return self.operations.get(op_name, {"done": False, "error": None})

    def ask_stream(
        self, question: str, store_names: list, metadata_filter: dict | None = None, model: str = "gemini-2.5-flash"
    ):
        if self.stream_should_fail:
            raise RuntimeError(self.stream_error)
        for chunk_text in self.stream_response:
            yield FakeStreamChunk(text=chunk_text)

    def new_stream_ids(self) -> tuple[str, str]:
        self._stream_counter += 1
        return (f"msg-{self._stream_counter}", f"txt-{self._stream_counter}")

    def extract_citations_from_response(self, response) -> list:
        return []

    def delete_document_from_store(self, *args, **kwargs) -> bool:
        return True

    # Test helpers
    def set_operation_error(self, op_name: str, error: str):
        self.operations[op_name] = {"done": True, "error": error}

    def set_operation_pending(self, op_name: str):
        self.operations[op_name] = {"done": False, "error": None}

    def reset(self):
        self.uploaded_files.clear()
        self.operations.clear()
        self._upload_counter = 0
        self.upload_should_fail = False
        self.stream_should_fail = False


class FakeGCSClient:
    """Fake GCS client."""

    def __init__(self):
        self.uploaded_blobs: list[dict] = []
        self._buckets: dict[str, "FakeGCSBucket"] = {}
        self.should_fail: bool = False
        self.fail_error: str = "Simulated GCS failure"

    def bucket(self, name: str) -> "FakeGCSBucket":
        if self.should_fail:
            raise RuntimeError(self.fail_error)
        if name not in self._buckets:
            self._buckets[name] = FakeGCSBucket(name, self)
        return self._buckets[name]

    def reset(self):
        self.uploaded_blobs.clear()
        self._buckets.clear()
        self.should_fail = False


class FakeGCSBucket:
    def __init__(self, name: str, client: FakeGCSClient):
        self.name = name
        self._client = client

    def blob(self, blob_name: str) -> "FakeGCSBlob":
        return FakeGCSBlob(blob_name, self)


class FakeGCSBlob:
    def __init__(self, name: str, bucket: FakeGCSBucket):
        self.name = name
        self._bucket = bucket

    def upload_from_filename(self, path: str):
        self._bucket._client.uploaded_blobs.append({"bucket": self._bucket.name, "blob": self.name, "source": path})
