# SPDX-License-Identifier: Apache-2.0
"""
Locust load test hitting the chat and upload flows with retry-safe polling.

Usage:
    locust -f scripts/load_test/locustfile.py --host http://localhost:8000

Env vars:
    TOKEN: Bearer token for authenticated requests (required)
    STORE_ID: Numeric store id to target uploads/chat (required)
    CHAT_MODEL: Optional model override
    REQUEST_TIMEOUT: Seconds for HTTP timeout (default: 30)
"""

from __future__ import annotations

import os
import random
import string
import time
from locust import HttpUser, task, between


TOKEN = os.getenv("TOKEN")
STORE_ID = os.getenv("STORE_ID")
CHAT_MODEL = os.getenv("CHAT_MODEL") or None
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT") or 30)


def _headers() -> dict:
    hdrs = {"X-Requested-With": "XMLHttpRequest"}
    if TOKEN:
        hdrs["Authorization"] = f"Bearer {TOKEN}"
    return hdrs


def _random_text(prefix: str) -> str:
    suffix = "".join(random.choice(string.ascii_lowercase) for _ in range(8))
    return f"{prefix}-{suffix}"


class RagUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        if not TOKEN or not STORE_ID:
            raise RuntimeError("TOKEN and STORE_ID env vars are required for load tests.")

    @task(4)
    def chat_task(self):
        payload = {
            "question": _random_text("What is the status of ticket"),
            "storeIds": [int(STORE_ID)],
        }
        if CHAT_MODEL:
            payload["model"] = CHAT_MODEL
        with self.client.post(
            "/api/chat",
            json=payload,
            headers=_headers(),
            timeout=REQUEST_TIMEOUT,
            catch_response=True,
            stream=True,
        ) as resp:
            # Consume stream to completion so Locust counts timing accurately
            try:
                for _chunk in resp.iter_lines():
                    if b"[DONE]" in _chunk:
                        break
            except Exception as exc:
                resp.failure(f"Chat stream error: {exc}")
            else:
                if not resp.ok:
                    resp.failure(f"Chat status {resp.status_code}")
                else:
                    resp.success()

    @task(1)
    def upload_task(self):
        # Minimal text file upload
        file_content = f"Sample content {_random_text('doc')}".encode()
        files = {"file": ("sample.txt", file_content, "text/plain")}
        data = {"storeId": STORE_ID, "displayName": "LoadTest Doc"}

        with self.client.post(
            "/api/upload",
            headers=_headers(),
            files=files,
            data=data,
            timeout=REQUEST_TIMEOUT,
            catch_response=True,
        ) as resp:
            if not resp.ok:
                resp.failure(f"Upload failed {resp.status_code}: {resp.text}")
                return
            body = resp.json()
            op_id = body.get("op_id")
            if not op_id:
                resp.failure("Missing op_id in upload response")
                return
            resp.success()

        # Poll op status until DONE/ERROR or timeout
        deadline = time.time() + 90
        while time.time() < deadline:
            op_resp = self.client.get(
                f"/api/upload/op-status/{op_id}",
                headers=_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            if not op_resp.ok:
                continue
            status = op_resp.json().get("status")
            if status in {"DONE", "ERROR"}:
                break
            time.sleep(1.5 + random.uniform(0, 0.5))

        if status != "DONE":
            self.environment.events.request.fire(
                request_type="UPLOAD_STATUS",
                name="/api/upload/op-status",
                response_time=0,
                response_length=0,
                exception=RuntimeError(f"Ingestion not DONE (status={status})"),
            )
