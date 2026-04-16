"""Background HTTP sender — queues payloads and ships them in a daemon thread."""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any

import httpx

_STOP = object()


class BackgroundSender:
    def __init__(self, api_url: str, token: str, max_queue: int = 1000) -> None:
        self._api_url = api_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._q: queue.Queue = queue.Queue(maxsize=max_queue)
        self._thread = threading.Thread(target=self._run, daemon=True, name="a2a-sender")
        self._thread.start()

    # ── Public ────────────────────────────────────────────────────────────────

    def enqueue(self, path: str, payload: dict[str, Any]) -> None:
        try:
            self._q.put_nowait((path, payload))
        except queue.Full:
            pass  # drop rather than block the agent

    def flush(self, timeout: float = 5.0) -> None:
        self._q.join()

    def shutdown(self, timeout: float = 5.0) -> None:
        self._q.put(_STOP)
        self._thread.join(timeout=timeout)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        with httpx.Client(timeout=10.0) as client:
            while True:
                item = self._q.get()
                if item is _STOP:
                    self._q.task_done()
                    break
                path, payload = item
                try:
                    client.post(
                        f"{self._api_url}{path}",
                        content=json.dumps(payload, default=str),
                        headers=self._headers,
                    )
                except Exception:
                    pass  # never crash the agent
                finally:
                    self._q.task_done()
