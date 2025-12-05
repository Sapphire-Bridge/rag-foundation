"""
Standalone benchmark runner that reuses the existing backend API:
- Auth via /api/auth/token (dev) or /api/auth/login (email+password) or pass --token
- Ensure a store exists (creates if missing)
- Optionally upload docs from a directory (PDFs) and poll indexing
- Run questions from a JSONL file through /api/chat (SSE), capture answers + citations
- Compute EM/F1/refusal/citation-hit and write JSONL/CSV + summary
"""
from __future__ import annotations

import argparse
import json
import concurrent.futures
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

from .metrics import (
    citation_hit,
    em_f1,
    extract_gold_doc_ids,
    mean,
    p95,
    refusal_ok,
)

DEFAULT_BASE_URL = "http://localhost:8000/api"


def _load_config(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise SystemExit("pyyaml is required to read benchmarks.yml (pip install pyyaml)") from exc
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"Invalid config in {path}")
    return data


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@dataclass
class BenchmarkDef:
    name: str
    display_name: str
    store_id: Optional[int]
    skip_upload: bool
    questions_path: Path
    docs_path: Optional[Path]
    docs_path_per_store: dict[str, Path]
    concurrency: int
    top_k: int
    language: Optional[str]
    max_questions: Optional[int]
    model: Optional[str] = None
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "BenchmarkDef":
        display = data.get("display_name") or data.get("store") or name
        return cls(
            name=name,
            display_name=display,
            store_id=data.get("store_id"),
            skip_upload=bool(data.get("skip_upload", False)),
            questions_path=Path(data["questions"]),
            docs_path=Path(data["docs_path"]) if data.get("docs_path") else None,
            docs_path_per_store={k: Path(v) for k, v in (data.get("docs_path_per_store") or {}).items()},
            concurrency=int(data.get("concurrency", 3)),
            top_k=int(data.get("top_k", 5)),
            language=data.get("language"),
            max_questions=data.get("max_questions"),
            model=data.get("model"),
            description=data.get("description"),
        )


class ApiClient:
    def __init__(self, base_url: str, token: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.session = httpx.Client(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Requested-With": "XMLHttpRequest",  # required by backend middleware
            },
        )

    @classmethod
    def from_credentials(cls, base_url: str, email: str, password: Optional[str]) -> "ApiClient":
        headers = {"X-Requested-With": "XMLHttpRequest"}
        if password:
            resp = httpx.post(
                f"{base_url.rstrip('/')}/auth/login",
                json={"email": email, "password": password},
                headers=headers,
                timeout=30,
            )
        else:
            resp = httpx.post(
                f"{base_url.rstrip('/')}/auth/token",
                json={"email": email},
                headers=headers,
                timeout=30,
            )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise SystemExit("Failed to fetch access token")
        return cls(base_url, token)

    def ensure_store(self, display_name: str, store_id: Optional[int] = None) -> int:
        if store_id:
            return int(store_id)
        resp = self.session.get(f"{self.base_url}/stores")
        resp.raise_for_status()
        for row in resp.json():
            if row.get("display_name") == display_name:
                return int(row["id"])
        created = self.session.post(f"{self.base_url}/stores", json={"display_name": display_name})
        created.raise_for_status()
        return int(created.json()["id"])

    def upload_and_poll(self, store_id: int, file_path: Path, max_mb: int, poll_timeout_s: int = 300) -> bool:
        # Best-effort MIME guess; backend allow-list must permit it.
        mime = "application/pdf" if file_path.suffix.lower() == ".pdf" else "text/plain"
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > max_mb:
            raise RuntimeError(f"File {file_path} exceeds max upload size {max_mb} MB")
        with file_path.open("rb") as fh:
            files = {"file": (file_path.name, fh, mime)}
        data = {"storeId": str(store_id), "displayName": file_path.stem}
        # Best-effort retry on transient errors.
        attempt = 0
        while True:
            attempt += 1
            resp = self.session.post(f"{self.base_url}/upload", data=data, files=files)
            if resp.status_code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            break
        op_id = resp.json()["op_id"]
        started = time.monotonic()
        while True:
            if time.monotonic() - started > poll_timeout_s:
                raise TimeoutError(f"Upload polling exceeded {poll_timeout_s}s for {file_path}")
            status_resp = self.session.get(f"{self.base_url}/upload/op-status/{op_id}")
            if status_resp.status_code in (429, 500, 502, 503):
                time.sleep(2)
                continue
            status_resp.raise_for_status()
            stat = status_resp.json().get("status")
            if stat in {"DONE", "ERROR"}:
                return stat == "DONE"
            time.sleep(2)

    def ask(
        self,
        store_id: int,
        question: str,
        timeout: Optional[int],
        model: Optional[str],
        top_k: int,
        language: Optional[str],
    ) -> tuple[str, list[dict], float, str]:
        headers = {"Accept": "text/event-stream"}
        answer_chunks: list[str] = []
        citations: list[dict] = []
        status = "ok"
        t0 = time.perf_counter()
        body = {"question": question, "storeIds": [store_id], "top_k": top_k}
        if model:
            body["model"] = model
        if language:
            body["language"] = language
        try:
            with self.session.stream(
                "POST",
                f"{self.base_url}/chat",
                json=body,
                headers=headers,
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                for raw in resp.iter_lines():
                    if not raw or raw.startswith(b":"):
                        continue
                    if raw == b"data: [DONE]":
                        break
                    if not raw.startswith(b"data:"):
                        continue
                    try:
                        payload = json.loads(raw.split(b": ", 1)[1])
                    except Exception:
                        status = "sse_parse_error"
                        continue
                    ptype = payload.get("type")
                    if ptype == "text-delta":
                        answer_chunks.append(payload.get("delta", ""))
                    elif ptype == "source-document":
                        citations.append(
                            {
                                "title": payload.get("title"),
                                "snippet": payload.get("snippet"),
                                "sourceId": payload.get("sourceId"),
                            }
                        )
                    elif ptype == "error":
                        status = payload.get("errorText", "error")
        except httpx.ReadTimeout:
            status = "timeout"
        except httpx.RequestError:
            status = "connection_error"
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        return "".join(answer_chunks).strip(), citations, latency_ms, status


def _upload_docs(
    client: ApiClient,
    store_id: int,
    docs_path: Optional[Path],
    skip: bool,
    sentinel: Optional[Path],
    max_upload_mb: int,
) -> None:
    if skip:
        print("[info] uploads skipped by config/flag")
        return
    if sentinel and sentinel.exists():
        print(f"[info] uploads previously completed (found {sentinel}); skipping")
        return
    if not docs_path:
        return
    if not docs_path.exists():
        print(f"[warn] docs_path {docs_path} does not exist; skipping uploads")
        return
    files = sorted(p for p in docs_path.glob("**/*") if p.is_file())
    if not files:
        print(f"[info] no files found under {docs_path}, skipping uploads")
        return
    all_ok = True
    for p in files:
        try:
            ok = client.upload_and_poll(store_id, p, max_upload_mb)
        except TimeoutError as exc:
            print(f"[upload] {p.name}: TIMEOUT ({exc})")
            ok = False
        except Exception as exc:
            print(f"[upload] {p.name}: ERROR ({exc})")
            ok = False
        print(f"[upload] {p.name}: {'DONE' if ok else 'ERROR'}")
        all_ok = all_ok and ok
    if sentinel and all_ok:
        try:
            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text("ok")
        except Exception:
            pass


def run_benchmark(
    client: ApiClient,
    bench: BenchmarkDef,
    out_dir: Path,
    limit: Optional[int] = None,
    timeout: Optional[int] = None,
    force_skip_upload: bool = False,
    max_upload_mb: int = 25,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    questions = _read_jsonl(bench.questions_path)
    max_q = bench.max_questions
    if limit is not None:
        max_q = min(limit, max_q) if max_q is not None else limit
    if max_q:
        questions = questions[:max_q]
    default_store_id = client.ensure_store(bench.display_name, bench.store_id)
    sentinel_default = (bench.docs_path or out_dir) / f".uploads.{bench.display_name}.done"
    _upload_docs(
        client,
        default_store_id,
        bench.docs_path,
        bench.skip_upload or force_skip_upload,
        sentinel_default,
        max_upload_mb,
    )

    # Cache store ids for per-record store routing.
    store_cache: dict[str, int] = {bench.display_name: default_store_id}
    uploaded_sentinels: set[str] = {str(sentinel_default)}

    def _run_one(idx: int, rec: dict) -> dict[str, Any]:
        qid = rec.get("id", f"q{idx}")
        gold = rec.get("answer")
        aliases: Iterable[str] = rec.get("aliases") or []
        expected_docs: list[str] = extract_gold_doc_ids(rec)
        is_unans = bool(rec.get("unanswerable")) or gold in (None, "")
        # Optional per-record store override
        record_store = rec.get("store")
        store_id = default_store_id
        store_name = bench.display_name
        if record_store:
            if isinstance(record_store, int):
                store_id = int(record_store)
                store_name = str(record_store)
            else:
                key = str(record_store)
                if key not in store_cache:
                    store_cache[key] = client.ensure_store(key)
                store_id = store_cache[key]
                store_name = key
            # Per-store docs upload if provided
            if bench.docs_path_per_store.get(store_name):
                doc_path = bench.docs_path_per_store[store_name]
                sentinel = (doc_path or out_dir) / f".uploads.{store_name}.done"
                if str(sentinel) not in uploaded_sentinels:
                    _upload_docs(
                        client,
                        store_id,
                        bench.docs_path_per_store[store_name],
                        bench.skip_upload or force_skip_upload,
                        sentinel,
                        max_upload_mb,
                    )
                    uploaded_sentinels.add(str(sentinel))
        try:
            attempt = 0
            while True:
                attempt += 1
                try:
                    model = rec.get("model") or bench.model
                    pred, cites, latency, status = client.ask(
                        store_id,
                        rec["question"],
                        timeout=timeout,
                        model=model,
                        top_k=bench.top_k,
                        language=bench.language,
                    )
                    break
                except httpx.HTTPStatusError as exc:
                    code = exc.response.status_code
                    if attempt < 3 and code in {429, 500, 502, 503}:
                        time.sleep(2 ** attempt)
                        continue
                    raise
        except httpx.HTTPStatusError as exc:
            pred, cites, latency, status = "", [], 0.0, f"http_error_{exc.response.status_code}"
        if is_unans:
            em, f1 = 0.0, 0.0
            refusal = refusal_ok(pred, True)
        else:
            em, f1 = em_f1(pred, gold, aliases)
            refusal = None
        recall = citation_hit(cites, expected_docs)
        return {
            "bench": bench.name,
            "store_display_name": store_name,
            "store_id": store_id,
            "id": qid,
            "question": rec["question"],
            "domain": rec.get("domain"),
            "difficulty": rec.get("difficulty"),
            "context_doc": rec.get("context_doc"),
            "expected_behavior": rec.get("expected_behavior"),
            "top_k": bench.top_k,
            "pred_answer": pred,
            "gold_answer": gold,
            "aliases": list(aliases),
            "em": em,
            "f1": f1,
            "refusal_ok": refusal,
            "unanswerable": is_unans,
            "citation_hit": recall,
            "citations": cites,
            "latency_ms": latency,
            "status": status,
            "model": rec.get("model") or bench.model,
        }

    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, bench.concurrency)) as executor:
        future_to_idx = {
            executor.submit(_run_one, idx, rec): idx for idx, rec in enumerate(questions, 1)
        }
        completed = 0
        total = len(future_to_idx)
        for fut in concurrent.futures.as_completed(future_to_idx):
            row = fut.result()
            results.append(row)
            if row["status"] == "ok":
                latencies.append(row["latency_ms"])
            completed += 1
            if completed % 10 == 0 or completed == total:
                print(f"[progress] {completed}/{total} completed")

    # Write outputs
    out_jsonl = out_dir / "results.jsonl"
    out_csv = out_dir / "results.csv"
    out_summary = out_dir / "summary.json"

    with out_jsonl.open("w") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if results:
        import csv

        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "bench",
                    "id",
                    "question",
                    "domain",
                    "difficulty",
                    "context_doc",
                    "expected_behavior",
                    "top_k",
                    "pred_answer",
                    "gold_answer",
                    "unanswerable",
                    "em",
                    "f1",
                    "refusal_ok",
                    "citation_hit",
                    "latency_ms",
                    "status",
                    "model",
                ],
            )
            writer.writeheader()
            for r in results:
                writer.writerow({k: r.get(k) for k in writer.fieldnames})

    em_scores = [r["em"] for r in results]
    f1_scores = [r["f1"] for r in results]
    refusal_scores = [int(r["refusal_ok"]) for r in results if r.get("refusal_ok") is not None]
    recalls = [r["citation_hit"] for r in results if r.get("citation_hit") is not None]
    errors = [r for r in results if r.get("status") != "ok"]
    summary = {
        "bench": bench.name,
        "model": bench.model,
        "top_k": bench.top_k,
        "language": bench.language,
        "count": len(results),
        "em": mean(em_scores),
        "f1": mean(f1_scores),
        "refusal_rate": mean(refusal_scores) if refusal_scores else None,
        "recall_at_citation": mean(recalls) if recalls else None,
        "citation_hit_rate": mean(recalls) if recalls else None,
        "avg_latency_ms": mean(latencies),
        "p95_latency_ms": p95(latencies),
        "error_rate": (len(errors) / len(results)) if results else 0.0,
    }
    out_summary.write_text(json.dumps(summary, indent=2))
    print(f"[done] wrote {out_jsonl}, {out_csv}, {out_summary}")
    print(f"[metrics] EM={summary['em']:.3f} F1={summary['f1']:.3f} avg_latency_ms={summary['avg_latency_ms']:.1f}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run RAG benchmarks against the local API.")
    p.add_argument("--bench", default="sample", help="Benchmark key from benchmarks.yml")
    p.add_argument("--config", default="scripts/benchmark/benchmarks.yml")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--email", help="Email for auth; uses /auth/token unless --password is set")
    p.add_argument("--password", help="Password for /auth/login (optional)")
    p.add_argument("--token", help="Existing bearer token (skips login)")
    p.add_argument("--out-dir", help="Output directory (defaults to artifacts/benchmarks/<bench>)")
    p.add_argument("--limit", type=int, help="Limit number of questions")
    p.add_argument("--timeout", type=int, help="Per-request timeout seconds (default 60)")
    p.add_argument("--skip-upload", action="store_true", help="Skip uploading docs even if docs_path is set")
    p.add_argument("--max-upload-mb", type=int, default=25, help="Max upload size per file (MB)")
    p.add_argument("--model", help="Override model to use for all questions")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = _load_config(Path(args.config))
    if args.bench not in cfg:
        raise SystemExit(f"Benchmark {args.bench} not found in {args.config}")
    bench = BenchmarkDef.from_dict(args.bench, cfg[args.bench])
    if args.model:
        bench.model = args.model
    token = args.token
    if not token:
        if not args.email:
            raise SystemExit("Provide --token or --email (with optional --password)")
        client = ApiClient.from_credentials(args.base_url, args.email, args.password)
    else:
        client = ApiClient(args.base_url, token)
    out_dir = Path(args.out_dir) if args.out_dir else Path("artifacts/benchmarks") / bench.name
    run_benchmark(
        client,
        bench,
        out_dir=out_dir,
        limit=args.limit,
        timeout=args.timeout,
        force_skip_upload=args.skip_upload,
        max_upload_mb=args.max_upload_mb,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
