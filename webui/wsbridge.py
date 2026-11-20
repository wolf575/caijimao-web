"""Backend WebSocket bridge -> in-process state cache -> browser SSE.

Wire format of the backend (verified):

    frame  = JSON array of strings
    item   = JSON string of {"<bus>": {"<Event>": <payload>}}
    bus    in {td_login_ws_bus, ecr_td_ws_bus, ecc_td_ws_bus,
               replace_td_ws_bus, va_td_ws_bus, button_bot_ws_bus}

So one frame can carry several events, and each event is double-encoded.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, AsyncIterator

import websockets

log = logging.getLogger("webui.ws")

MAX_EVENTS = 400


class WsBridge:
    def __init__(self, url: str = "ws://127.0.0.1:3333/ws", state_path: str | Path | None = None) -> None:
        self.url = url
        self.state: dict[str, dict[str, Any]] = {}
        self.events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self._subs: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.connected = False
        self.last_error: str | None = None
        self.frames = 0
        # 后端只在「状态变化」时推 IsVip，Web 端重启会漏掉历史值；
        # 把已知的模块状态落盘，重启后仍能显示上次的判定结果。
        self.state_path = Path(state_path) if state_path else None
        self._vip: dict[int, bool] = {}
        self._load_vip()

    # ----------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run(), name="wsbridge")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                async with websockets.connect(
                    self.url, ping_interval=20, ping_timeout=20, max_queue=256
                ) as ws:
                    self.connected = True
                    self.last_error = None
                    delay = 1.0
                    log.info("已连接后端 WS: %s", self.url)
                    while not self._stop.is_set():
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        self._ingest(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect on anything
                self.connected = False
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.debug("WS 断开: %s", self.last_error)
            finally:
                self.connected = False
            if self._stop.is_set():
                break
            await asyncio.sleep(delay)
            delay = min(delay * 1.8, 30.0)

    # ------------------------------------------------------------- parsing

    def _ingest(self, raw: str | bytes) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        try:
            outer = json.loads(raw)
        except json.JSONDecodeError:
            return
        items = outer if isinstance(outer, list) else [outer]
        for item in items:
            event = item
            if isinstance(item, str):
                try:
                    event = json.loads(item)
                except json.JSONDecodeError:
                    continue
            if not isinstance(event, dict):
                continue
            for bus, payload in event.items():
                if not isinstance(payload, dict):
                    continue
                slot = self.state.setdefault(bus, {})
                for key, value in payload.items():
                    slot[key] = value
                    if key == "IsVip" and isinstance(value, dict) and "module_id" in value:
                        with contextlib.suppress(TypeError, ValueError):
                            self._vip[int(value["module_id"])] = bool(value.get("is_vip"))
                            self._save_vip()
                    record = {
                        "t": time.time(),
                        "bus": bus,
                        "event": key,
                        "data": value,
                    }
                    self.events.append(record)
                    self._broadcast(record)
        self.frames += 1

    # ------------------------------------------------------ vip persistence

    def _load_vip(self) -> None:
        if self.state_path is None:
            return
        try:
            raw = json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            for k, v in raw.items():
                with contextlib.suppress(TypeError, ValueError):
                    self._vip[int(k)] = bool(v)

    def _save_vip(self) -> None:
        if self.state_path is None:
            return
        tmp = self.state_path.with_suffix(".tmp")
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(
                json.dumps({str(k): v for k, v in sorted(self._vip.items())}, ensure_ascii=False),
                "utf-8",
            )
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    def _broadcast(self, record: dict[str, Any]) -> None:
        dead: list[asyncio.Queue] = []
        for queue in self._subs:
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            self._subs.discard(queue)

    # ------------------------------------------------------------ read api

    def snapshot(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "last_error": self.last_error,
            "frames": self.frames,
            "buses": self.state,
        }

    def is_vip(self) -> dict[int, bool]:
        """Collapse the IsVip events into {module_id: bool}."""
        out: dict[int, bool] = dict(self._vip)
        for bus, payload in self.state.items():
            vip = payload.get("IsVip")
            if isinstance(vip, dict) and "module_id" in vip:
                with contextlib.suppress(TypeError, ValueError):
                    out[int(vip["module_id"])] = bool(vip.get("is_vip"))
        return out

    def latest(self, bus: str, event: str) -> Any:
        return self.state.get(bus, {}).get(event)

    def recent(self, limit: int = 60) -> list[dict[str, Any]]:
        return list(self.events)[-limit:]

    # --------------------------------------------------------------- SSE

    @contextlib.asynccontextmanager
    async def subscription(self) -> AsyncIterator[asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subs.add(queue)
        try:
            yield queue
        finally:
            self._subs.discard(queue)

    async def stream(self, heartbeat: float = 15.0) -> AsyncIterator[str]:
        async with self.subscription() as queue:
            yield _sse("hello", self.snapshot())
            while True:
                try:
                    record = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse("event", record)


def _sse(event: str, data: Any) -> str:
    body = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {body}\n\n"
