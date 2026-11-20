"""采集猫 Web 控制台 —— FastAPI 应用。

启动：uvicorn webui.app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import parity
from .auth import COOKIE_NAME, Auth, Session
from .backend import BackendClient
from .wsbridge import WsBridge

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("webui")

DATA_DIR = Path(os.environ.get("CJ_DATA_DIR", "./data"))
APP_DIR = Path(os.environ.get("CJ_APP_DIR", "./app"))
BACKEND_HTTP = os.environ.get("CJ_BACKEND_HTTP", "http://127.0.0.1:3334")
BACKEND_WS = os.environ.get("CJ_BACKEND_WS", "ws://127.0.0.1:3333/ws")

auth = Auth(DATA_DIR)
backend = BackendClient(BACKEND_HTTP, logs_dir=APP_DIR / "logs")
bridge = WsBridge(BACKEND_WS, state_path=DATA_DIR / "is_vip.json")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["nav"] = parity.nav
templates.env.globals["channels"] = parity.CHANNELS
templates.env.globals["console_only"] = parity.console_only


# ---------------------------------------------------------------- lifespan


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    auth.bootstrap()
    await backend.start()
    await bridge.start()

    async def _warm():
        ok = await backend.wait_ready(timeout=90)
        log.info("后端就绪: %s", ok)

    task = asyncio.create_task(_warm())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await bridge.stop()
        await backend.close()


app = FastAPI(title="采集猫 Web 控制台", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ------------------------------------------------------------------ errors


@app.exception_handler(HTTPException)
async def _http_error(request: Request, exc: HTTPException):
    if exc.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
        wants_json = request.url.path.startswith("/api/") or "application/json" in (
            request.headers.get("accept") or ""
        )
        if wants_json:
            return JSONResponse(
                {"ok": False, "error": "unauthorized", "detail": exc.detail},
                status_code=exc.status_code,
            )
        target = f"/login?next={quote(request.url.path)}"
        return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    return JSONResponse(
        {"ok": False, "error": exc.detail}, status_code=exc.status_code
    )


def guard(request: Request) -> Session:
    return auth.require(request)


def _ctx(request: Request, session: Session, **extra: Any) -> dict[str, Any]:
    base = {
        "request": request,
        "user": session.user,
        "csrf": session.csrf,
        "active": request.url.path,
        "is_vip": bridge.is_vip(),
        "ws_connected": bridge.connected,
    }
    base.update(extra)
    return base


# ------------------------------------------------------------------- auth


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if auth.session_of(request) is not None:
        return RedirectResponse(next or "/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "error": None, "next": next, "active": "/login"},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    ip = Auth.client_ip(request)
    if auth.limiter.locked(ip):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "error": "失败次数过多，请 5 分钟后再试",
                "next": next,
                "active": "/login",
            },
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    session = auth.verify(username, password, ip)
    if session is None:
        await asyncio.sleep(0.3)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "request": request,
                "error": "用户名或密码错误",
                "next": next,
                "active": "/login",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    token, _ = auth.issue(session.user)
    response = RedirectResponse(next or "/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=auth.session_seconds,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("CJ_COOKIE_SECURE", "0") == "1",
        path="/",
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


# ------------------------------------------------------------------- pages


@app.get("/", response_class=HTMLResponse)
async def page_index(request: Request, session: Session = Depends(guard)):
    lease = await backend.get_json("td_web_req", "GetLease")
    hd = await backend.get_json("td_web_req", "GetHD")
    version = await backend.get_json("td_web_req", "GetVersion")
    return templates.TemplateResponse(
        request,
        "index.html",
        _ctx(
            request,
            session,
            lease=lease,
            hd=hd,
            version=version,
            backend_ok=await backend.ping(),
            snapshot=bridge.snapshot(),
        ),
    )


@app.get("/td-login", response_class=HTMLResponse)
async def page_td_login(request: Request, session: Session = Depends(guard)):
    chats = await backend.get_json("td_web_req", "GetMyChatsFull")
    ant = await backend.get_json("td_web_req", "GetAntConfig")
    return templates.TemplateResponse(
        request,
        "td_login.html",
        _ctx(request, session, chats=chats, ant=ant, snapshot=bridge.snapshot()),
    )


SERVICE_ROUTES = {
    "/ecr": ("ecr_td_web_req", "爬虫PRO", "StartService", "StopService"),
    "/ecc": ("ecc_td_web_req", "频道群克隆PRO", "StartService", "StopService"),
    "/replace": ("replace_td_web_req", "批量替换/删除服务", "StartService", "StopService"),
    "/va": ("va_td_web_req", "付费群助手", "StartService", "StopService"),
    "/btn-bot": ("button_bot_web_req", "按钮机器人服务", "StartBot", "StopBot"),
}


def _service_page(template: str):
    async def handler(request: Request, session: Session = Depends(guard)):
        channel, label, start, stop = SERVICE_ROUTES[request.url.path]
        cfg = await backend.get_json(channel, "GetCfg")
        stats = await backend.get_json(channel, "GetTaskStats")
        backups = await backend.get_json(channel, "GetBackupFiles")
        return templates.TemplateResponse(
            request,
            template,
            _ctx(
                request,
                session,
                channel=channel,
                label=label,
                start_action=start,
                stop_action=stop,
                cfg=cfg,
                stats=stats,
                backups=backups,
                snapshot=bridge.snapshot(),
            ),
        )

    return handler


for _path in SERVICE_ROUTES:
    app.add_api_route(
        _path,
        _service_page("service.html"),
        methods=["GET"],
        response_class=HTMLResponse,
    )


@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request, session: Session = Depends(guard)):
    ant = await backend.get_json("td_web_req", "GetAntConfig")
    encoder = await backend.get_json("td_web_req", "GetEncoder")
    threads = await backend.get_json("td_web_req", "GetFFMpegThreadCount")
    speed = await backend.get_json("td_web_req", "GetFFMpegSpeedDecode")
    sqlite_off = await backend.get_json("td_web_req", "GetSqliteSyncOff")
    host = await backend.get_json("td_web_req", "GetHostCfg")
    name_repl = await backend.get_json("td_web_req", "GetFileNameReplaces")
    hd = await backend.get_json("td_web_req", "GetHD")
    return templates.TemplateResponse(
        request,
        "settings.html",
        _ctx(
            request,
            session,
            ant=ant,
            encoder=encoder,
            threads=threads,
            speed=speed,
            sqlite_off=sqlite_off,
            host=host,
            name_repl=name_repl,
            hd=hd,
            snapshot=bridge.snapshot(),
        ),
    )


@app.get("/logs", response_class=HTMLResponse)
async def page_logs(request: Request, session: Session = Depends(guard), kind: str = "sys"):
    path = backend.syslog_path() if kind == "sys" else backend._newest_errlog()
    return templates.TemplateResponse(
        request,
        "logs.html",
        _ctx(
            request,
            session,
            kind=kind,
            path=str(path) if path else None,
            text=backend.tail(path, 120_000),
        ),
    )


@app.get("/admin/console", response_class=HTMLResponse)
async def page_console(request: Request, session: Session = Depends(guard)):
    return templates.TemplateResponse(
        request,
        "console.html",
        _ctx(
            request,
            session,
            problems=parity.selfcheck(),
            total=parity.total_actions(),
            console_only=parity.console_only(),
        ),
    )


# --------------------------------------------------------------------- api


def _coerce(raw: str) -> Any:
    text = (raw or "").strip()
    if text == "":
        return 1
    if text in ("true", "false"):
        return text == "true"
    if text.lstrip("-").isdigit():
        return int(text)
    if text[0] in "{[":
        return json.loads(text)
    return text


@app.post("/api/action")
async def api_action(
    request: Request,
    session: Session = Depends(guard),
    channel: str = Form(...),
    action: str = Form(...),
    value: str = Form("1"),
    csrf_token: str = Form(""),
):
    if not auth.check_csrf(session, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf"}, status_code=400)
    if channel not in parity.BY_KEY:
        return JSONResponse({"ok": False, "error": "unknown channel"}, status_code=400)
    if action not in parity.BY_KEY[channel].actions:
        return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
    try:
        parsed = _coerce(value)
    except json.JSONDecodeError as exc:
        return JSONResponse({"ok": False, "error": f"payload 不是合法 JSON: {exc}"}, status_code=400)
    result = await backend.call(channel, action, parsed)
    log.info("action user=%s %s.%s value=%r ok=%s", session.user, channel, action, parsed, result["ok"])
    return JSONResponse(result)


@app.get("/api/state")
async def api_state(session: Session = Depends(guard)):
    return JSONResponse(
        {
            "ok": True,
            "backend_ok": await backend.ping(),
            "is_vip": bridge.is_vip(),
            "snapshot": bridge.snapshot(),
            "recent": bridge.recent(80),
        }
    )


@app.get("/api/stream")
async def api_stream(session: Session = Depends(guard)):
    return StreamingResponse(
        bridge.stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/logs")
async def api_logs(session: Session = Depends(guard), kind: str = "sys", lines: int = 200):
    path = backend.syslog_path() if kind == "sys" else backend._newest_errlog()
    text = backend.tail(path, 400_000)
    rows = [ln for ln in text.splitlines() if ln.strip()]
    return JSONResponse(
        {"ok": True, "path": str(path) if path else None, "lines": rows[-lines:]}
    )


@app.get("/api/parity")
async def api_parity(session: Session = Depends(guard)):
    return JSONResponse(
        {
            "ok": True,
            "channels": len(parity.CHANNELS),
            "actions": parity.total_actions(),
            "problems": parity.selfcheck(),
            "console_only": parity.console_only(),
        }
    )


@app.get("/healthz")
async def healthz():
    ok = await backend.ping(timeout=2.0)
    return JSONResponse(
        {"ok": ok, "backend": ok, "ws": bridge.connected},
        status_code=200 if ok else 503,
    )
