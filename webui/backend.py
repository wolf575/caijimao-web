"""Thin async client for the 采集猫 backend.

The backend is a single HTTP endpoint plus one WebSocket:

    POST http://127.0.0.1:3334/req   body: {"<channel>": {"<Action>": <value>}}
    GET  http://127.0.0.1:3334/ping  -> "pong"
    WS   ws://127.0.0.1:3333/ws      -> JSON array of JSON strings

Important quirk (verified against the shipped binary): the HTTP layer answers
`ok` for *unknown* action names too, so a 200 is not proof of success.  Real
errors are only written to `app/logs/err.<date>.log`.  `call()` therefore
snapshots that file and returns whatever new lines appeared, which is the only
honest success signal we have.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from .parity import BY_KEY
from .payloads import build as build_payload

_UNSET = object()


class BackendError(RuntimeError):
    pass


def _parse(text: str) -> Any:
    body = text.strip()
    if not body:
        return None
    if body[0] in "{[":
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body
    return body


class BackendClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:3334",
        logs_dir: str | Path = "logs",
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.logs_dir = Path(logs_dir)
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self._timeout, connect=5.0),
                headers={"Content-Type": "application/json"},
                # 后端永远在本机回环口，绝不能走环境里的 HTTP(S)_PROXY；
                # 某些 Windows 环境里 NO_PROXY=[::1] 还会让 httpx 直接崩。
                trust_env=False,
            )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---------------------------------------------------------------- health

    async def ping(self, timeout: float = 3.0) -> bool:
        if self._client is None:
            await self.start()
        assert self._client is not None
        try:
            r = await self._client.get("/ping", timeout=timeout)
        except httpx.HTTPError:
            return False
        return "pong" in r.text.lower()

    async def wait_ready(self, timeout: float = 60.0, interval: float = 1.0) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if await self.ping():
                return True
            await asyncio.sleep(interval)
        return False

    # ------------------------------------------------------------ error log

    def _newest_errlog(self) -> Path | None:
        try:
            files = sorted(
                self.logs_dir.glob("err.*.log"), key=lambda p: p.stat().st_mtime
            )
        except OSError:
            return None
        return files[-1] if files else None

    def _err_offset(self) -> tuple[Path | None, int]:
        path = self._newest_errlog()
        if path is None:
            return None, 0
        try:
            return path, path.stat().st_size
        except OSError:
            return path, 0

    @staticmethod
    def _read_from(path: Path | None, offset: int, limit: int = 8192) -> str:
        if path is None:
            return ""
        try:
            with path.open("rb") as fh:
                fh.seek(offset)
                data = fh.read(limit)
        except OSError:
            return ""
        return data.decode("utf-8", "replace").strip()

    # ---------------------------------------------------------------- calls

    async def call(
        self,
        channel: str,
        action: str,
        value: Any = _UNSET,
        capture_errors: bool = True,
    ) -> dict[str, Any]:
        if channel not in BY_KEY:
            raise BackendError(f"unknown channel {channel!r}")
        if self._client is None:
            await self.start()
        assert self._client is not None

        # 没显式给 value 时按官方客户端的入参规格构造，否则一律发 1 会在 err.log 里
        # 留下一堆 deserialize_err（例如 GetMyChatsFull 要 bool、StartCfgRows 要数组）。
        if value is _UNSET:
            value = build_payload(channel, action, {})

        path, offset = self._err_offset() if capture_errors else (None, 0)
        payload = {channel: {action: value}}
        try:
            r = await self._client.post("/req", json=payload)
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "transport_error": str(exc),
                "channel": channel,
                "action": action,
                "data": None,
                "errors": "",
            }

        errors = ""
        if capture_errors:
            # the backend writes the log line before answering, but be generous
            for _ in range(10):
                errors = self._read_from(path, offset)
                if errors:
                    break
                await asyncio.sleep(0.02)

        data = _parse(r.text)
        ok = r.status_code < 400 and (data == "ok" or isinstance(data, (dict, list)))
        return {
            "ok": ok,
            "status": r.status_code,
            "channel": channel,
            "action": action,
            "data": data,
            "errors": errors,
        }

    async def get_json(self, channel: str, action: str, value: Any = _UNSET) -> Any:
        res = await self.call(channel, action, value, capture_errors=False)
        return res.get("data")

    # ----------------------------------------------------------- log tails

    def syslog_path(self) -> Path | None:
        try:
            files = sorted(
                self.logs_dir.glob("sys.log.*"), key=lambda p: p.stat().st_mtime
            )
        except OSError:
            return None
        return files[-1] if files else None

    def tail(self, path: Path | None, max_bytes: int = 65536) -> str:
        if path is None:
            return ""
        try:
            size = path.stat().st_size
            with path.open("rb") as fh:
                if size > max_bytes:
                    fh.seek(size - max_bytes)
                data = fh.read()
        except OSError:
            return ""
        text = data.decode("utf-8", "replace")
        if size_trimmed := (len(data) < size):
            text = text.split("\n", 1)[-1] if size_trimmed else text
        return text
