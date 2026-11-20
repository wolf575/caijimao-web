"""用 CDP 给 Web 控制台截图（登录态）。

流程：httpx 登录拿 cookie -> 启动 headless chrome -> CDP 注入 cookie -> 导航 -> 截图
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

BASE = "http://127.0.0.1:8080"
USER = os.environ.get("WEB_USER", "admin")
PASS = os.environ.get("WEB_PASSWORD", "test-pass-1234")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "shot")
PAGES = sys.argv[2:] or ["/"]


async def cdp(ws_url: str, messages: list[dict]) -> dict:
    async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
        out = {}
        for i, msg in enumerate(messages):
            msg["id"] = i + 1
            await ws.send(json.dumps(msg))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(raw)
                if data.get("id") == msg["id"]:
                    out[msg["method"]] = data
                    break
        return out


async def main() -> None:
    with httpx.Client(trust_env=False, timeout=20, follow_redirects=False) as c:
        r = c.post(f"{BASE}/login", data={"username": USER, "password": PASS, "next": "/"})
        if r.status_code != 303:
            raise SystemExit(f"login failed: {r.status_code}")
        token = c.cookies.get("cj_session")
        if not token:
            raise SystemExit("no session cookie")

    profile = tempfile.mkdtemp(prefix="cjchrome")
    proc = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            "--remote-debugging-port=9222",
            "--window-size=1500,980",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        ver = None
        for _ in range(60):
            time.sleep(0.3)
            try:
                ver = httpx.get("http://127.0.0.1:9222/json/version", trust_env=False, timeout=2).json()
                break
            except Exception:  # noqa: BLE001
                continue
        if not ver:
            raise SystemExit("chrome devtools not reachable")
        browser_ws = ver["webSocketDebuggerUrl"]

        OUT.mkdir(parents=True, exist_ok=True)
        for page in PAGES:
            name = (page.strip("/").replace("/", "_").replace("?", "_") or "index") + ".png"
            target = await cdp(browser_ws, [{"method": "Target.createTarget", "params": {"url": "about:blank"}}])
            tid = target["Target.createTarget"]["result"]["targetId"]
            page_ws = f"ws://127.0.0.1:9222/devtools/page/{tid}"
            await cdp(
                page_ws,
                [
                    {"method": "Page.enable", "params": {}},
                    {"method": "Emulation.setDeviceMetricsOverride",
                     "params": {"width": 1500, "height": 980, "deviceScaleFactor": 1, "mobile": False}},
                    {"method": "Network.enable", "params": {}},
                    {"method": "Network.setCookie",
                     "params": {"name": "cj_session", "value": token, "domain": "127.0.0.1",
                                "path": "/", "httpOnly": True}},
                    {"method": "Page.navigate", "params": {"url": BASE + page}},
                ],
            )
            await asyncio.sleep(3.0)
            shot = await cdp(page_ws, [{"method": "Page.captureScreenshot", "params": {"format": "png"}}])
            data = shot["Page.captureScreenshot"]["result"]["data"]
            path = OUT / name
            path.write_bytes(base64.b64decode(data))
            print(f"{page:24} -> {path} ({path.stat().st_size} bytes)")
            await cdp(browser_ws, [{"method": "Target.closeTarget", "params": {"targetId": tid}}])
    finally:
        proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
