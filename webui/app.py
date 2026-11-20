"""采集猫 Web 控制台 —— FastAPI 应用。

启动：uvicorn webui.app:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import cfgmodel, parity, payloads
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


PROXIES_FILE = "ui-proxy.yml"
ANT_FILE = "ui-cfg.yml"


def _read_ant() -> dict[str, Any]:
    """极简 YAML 读取：ui-cfg.yml 只有 6 个扁平标量键，不值得引入依赖。"""
    out: dict[str, Any] = {
        "api_id": "", "api_hash": "", "req_limit": 35,
        "phone": "", "hide_phone": False, "proxy": None,
    }
    try:
        text = (APP_DIR / ANT_FILE).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v in ("''", '""', "null", "~", ""):
            out[k] = "" if k != "proxy" else None
        elif v in ("true", "false"):
            out[k] = v == "true"
        else:
            out[k] = v.strip("'\"")
    return out


def _write_ant(cfg: dict[str, Any]) -> None:
    def q(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        return "'" + str(v).replace("'", "''") + "'"

    body = "".join(
        f"{k}: {q(cfg.get(k))}\n"
        for k in ("api_id", "api_hash", "req_limit", "phone", "hide_phone", "proxy")
    )
    path = APP_DIR / ANT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


@app.post("/api/antcfg")
async def api_antcfg(request: Request, session: Session = Depends(guard)):
    """ui-cfg.yml 直接落盘 + ReloadCfg。后端 FlushAntConfig 的入参形状不可靠（会把
    电话号码截成 '+'、req_limit 变 0），所以这里走文件，和桌面版行为一致。"""
    form = await request.form()
    if not auth.check_csrf(session, str(form.get("csrf_token") or "")):
        return JSONResponse({"ok": False, "error": "csrf"}, status_code=400)
    cur = _read_ant()
    phone = str(form.get("phone") or "").strip()
    if phone and not re.fullmatch(r"\+\d{6,20}", phone):
        return JSONResponse({"ok": False, "error": "电话号码要以 + 和国家代码开头，例如 +8613xxxxxxxxx"},
                            status_code=400)
    try:
        req_limit = int(str(form.get("req_limit") or cur.get("req_limit") or 35))
    except ValueError:
        req_limit = 35
    cfg = {
        "api_id": str(form.get("api_id") if form.get("api_id") is not None else cur.get("api_id", "")),
        "api_hash": str(form.get("api_hash") if form.get("api_hash") is not None else cur.get("api_hash", "")),
        "req_limit": req_limit if req_limit > 0 else 35,
        "phone": phone if phone else cur.get("phone", ""),
        "hide_phone": str(form.get("hide_phone") or "").lower() in ("1", "true", "on", "yes")
        if "hide_phone" in form else bool(cur.get("hide_phone")),
        "proxy": cur.get("proxy"),
    }
    try:
        _write_ant(cfg)
    except OSError as exc:
        return JSONResponse({"ok": False, "error": f"写入失败: {exc}"}, status_code=500)
    log.info("antcfg user=%s phone=%s req_limit=%s", session.user, cfg["phone"], cfg["req_limit"])
    # ReloadCfg 有时会让后端短暂断开，异步触发即可，不要让页面等它
    asyncio.create_task(_reload_cfg_quiet())
    return RedirectResponse("/td-login", status_code=303)


async def _reload_cfg_quiet() -> None:
    try:
        await backend.call("td_web_req", "ReloadCfg", True)
    except Exception as exc:  # noqa: BLE001 - 重载失败不影响已落盘的配置
        log.warning("reload cfg failed: %s", exc)


def _read_proxies() -> tuple[str, str]:
    """返回 (编辑器文本, 文件当前内容)。"""
    path = APP_DIR / PROXIES_FILE
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        raw = "[]\n"
    try:
        text = json.dumps(json.loads(raw or "[]"), ensure_ascii=False, indent=2)
    except ValueError:
        text = raw.strip() or "[]"
    return text, (raw.strip() or "[]")


@app.get("/td-login", response_class=HTMLResponse)
async def page_td_login(request: Request, session: Session = Depends(guard)):
    chats = await backend.get_json("td_web_req", "GetMyChatsFull")
    ant = await backend.get_json("td_web_req", "GetAntConfig")
    proxies_text, proxies_file = _read_proxies()
    return templates.TemplateResponse(
        request,
        "td_login.html",
        _ctx(
            request,
            session,
            chats=chats,
            ant=ant,
            proxies_text=proxies_text,
            proxies_file=proxies_file,
            antcfg=_read_ant(),
            snapshot=bridge.snapshot(),
        ),
    )


@app.post("/api/proxies")
async def api_proxies(request: Request, session: Session = Depends(guard)):
    """代理列表要落盘到 app/ui-proxy.yml，后端只接受一个「重新加载」的 bool。"""
    form = await request.form()
    if not auth.check_csrf(session, str(form.get("csrf_token") or "")):
        return JSONResponse({"ok": False, "error": "csrf"}, status_code=400)
    raw = str(form.get("proxies") or "").strip() or "[]"
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": f"JSON 解析失败: {exc}"}, status_code=400)
    if not isinstance(data, list):
        return JSONResponse({"ok": False, "error": "必须是一个 JSON 数组"}, status_code=400)
    path = APP_DIR / PROXIES_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        return JSONResponse({"ok": False, "error": f"写入失败: {exc}"}, status_code=500)
    # 后端要的是代理数组本身（不是 bool）；同时把内容落到 ui-proxy.yml，重启后仍生效。
    result = await backend.call("td_web_req", "FlushUiProxies", data)
    log.info("proxies user=%s count=%d reload_ok=%s", session.user, len(data), result["ok"])
    return RedirectResponse("/td-login", status_code=303)


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
        spec = parity.BY_KEY[channel]
        cfg = await backend.get_json(channel, "GetCfg")
        # 只有部分通道支持 GetTaskStats，无脑调用会往 err.log 写 deserialize_err
        stats = None
        if "GetTaskStats" in spec.actions:
            stats = await backend.get_json(channel, "GetTaskStats")
        backups = None
        if "GetBackupFiles" in spec.actions:
            backups = await backend.get_json(channel, "GetBackupFiles")
        rows: list[dict[str, Any]] = []
        if cfgmodel.has_row_api(channel) and isinstance(cfg, dict):
            for row in cfg.get(cfgmodel.list_key(channel)) or []:
                if isinstance(row, dict):
                    rows.append(cfgmodel.brief(row, channel))
        return templates.TemplateResponse(
            request,
            template,
            _ctx(
                request,
                session,
                channel=channel,
                c=spec,
                label=label,
                start_action=start,
                stop_action=stop,
                cfg=cfg,
                stats=stats,
                backups=backups,
                rows=rows,
                model=cfgmodel.model(channel),
                row_api=cfgmodel.has_row_api(channel),
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
async def api_action(request: Request, session: Session = Depends(guard)):
    form = await request.form()
    csrf_token = str(form.get("csrf_token", ""))
    if not auth.check_csrf(session, csrf_token):
        return JSONResponse({"ok": False, "error": "csrf"}, status_code=400)
    channel = str(form.get("channel", ""))
    action = str(form.get("action", ""))
    if channel not in parity.BY_KEY:
        return JSONResponse({"ok": False, "error": "unknown channel"}, status_code=400)
    if action not in parity.BY_KEY[channel].actions:
        return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
    fields = {k: str(v) for k, v in form.items() if k not in ("csrf_token", "channel", "action")}
    try:
        parsed = payloads.build(channel, action, fields)
    except Exception as exc:  # 值类型不对时直接告诉用户怎么填
        return JSONResponse(
            {
                "ok": False,
                "error": f"参数格式不对：{exc}",
                "hint": payloads.describe(channel, action),
            },
            status_code=400,
        )
    result = await backend.call(channel, action, parsed)
    log.info("action user=%s %s.%s value=%r ok=%s", session.user, channel, action, parsed, result["ok"])
    if not result.get("errors") and result.get("ok"):
        result["hint"] = payloads.describe(channel, action)
    return JSONResponse(result)


@app.get("/api/spec")
async def api_spec(session: Session = Depends(guard), channel: str = "", action: str = ""):
    """返回某个动作需要的表单字段，前端据此渲染输入框。"""
    if channel not in parity.BY_KEY:
        return JSONResponse({"ok": False, "error": "unknown channel"}, status_code=400)
    sp = dict(payloads.spec_of(channel, action))
    sp.pop("fields", None)
    sp["fields"] = list(payloads.spec_of(channel, action).get("fields", ()))
    return JSONResponse({"ok": True, "spec": sp})


# ------------------------------------------------------------- config rows


async def _fetch_rows(channel: str) -> list[dict[str, Any]]:
    cfg = await backend.get_json(channel, "GetCfg")
    out: list[dict[str, Any]] = []
    if isinstance(cfg, dict):
        for row in cfg.get(cfgmodel.list_key(channel)) or []:
            if isinstance(row, dict):
                out.append(row)
    return out


@app.get("/api/cfg")
async def api_cfg(session: Session = Depends(guard), channel: str = ""):
    if channel not in parity.BY_KEY:
        return JSONResponse({"ok": False, "error": "unknown channel"}, status_code=400)
    rows = await _fetch_rows(channel)
    return JSONResponse(
        {
            "ok": True,
            "channel": channel,
            "rows": [cfgmodel.brief(r, channel) for r in rows],
        }
    )


@app.get("/api/cfg/row")
async def api_cfg_row(session: Session = Depends(guard), channel: str = "", id: int = 0):
    if channel not in parity.BY_KEY:
        return JSONResponse({"ok": False, "error": "unknown channel"}, status_code=400)
    if cfgmodel.is_whole(channel):
        cfg = await backend.get_json(channel, "GetCfg")
        if not isinstance(cfg, dict):
            cfg = cfgmodel.whole_config(channel)
        return JSONResponse({"ok": True, "channel": channel, "id": 0, "whole": True, "row": cfg})
    if not cfgmodel.has_row_api(channel):
        return JSONResponse({"ok": False, "error": "该通道不支持配置行"}, status_code=400)
    if id:
        detail = await backend.call(channel, "GetCfgRow", id)
        row = detail.get("data")
    else:
        row = cfgmodel.template(channel)
    if row is None:
        return JSONResponse({"ok": False, "error": "没有找到配置模板"}, status_code=404)
    return JSONResponse({"ok": True, "channel": channel, "id": id, "row": row})


@app.post("/api/cfg/save")
async def api_cfg_save(request: Request, session: Session = Depends(guard)):
    form = await request.form()
    if not auth.check_csrf(session, str(form.get("csrf_token", ""))):
        return JSONResponse({"ok": False, "error": "csrf"}, status_code=400)
    channel = str(form.get("channel", ""))
    mode = str(form.get("mode", "add"))
    if channel not in parity.BY_KEY:
        return JSONResponse({"ok": False, "error": "unknown channel"}, status_code=400)

    # replace_td / button_bot 只能整份配置 FlushCfg
    if cfgmodel.is_whole(channel):
        raw = str(form.get("config", "") or "")
        if not raw.strip():
            return JSONResponse({"ok": False, "error": "配置内容为空"}, status_code=400)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            return JSONResponse({"ok": False, "error": f"不是合法 JSON：{exc}"}, status_code=400)
        if not isinstance(parsed, dict):
            return JSONResponse({"ok": False, "error": "顶层必须是对象"}, status_code=400)
        result = await backend.call(channel, "FlushCfg", parsed)
        if result.get("errors"):
            return JSONResponse(
                {"ok": False, "error": "后端拒绝了这份配置", "detail": result.get("errors")},
                status_code=400,
            )
        log.info("cfg flush user=%s %s whole", session.user, channel)
        return JSONResponse({"ok": True, "mode": "whole", "result": result})

    if not cfgmodel.has_row_api(channel):
        return JSONResponse({"ok": False, "error": "该通道不支持配置行"}, status_code=400)

    fields = {k: str(v) for k, v in form.items()}
    base = None
    if mode == "update":
        row_id = int(str(form.get("id") or 0))
        if row_id <= 0:
            return JSONResponse({"ok": False, "error": "缺少配置行 id"}, status_code=400)
        detail = await backend.call(channel, "GetCfgRow", row_id)
        if not isinstance(detail.get("data"), dict):
            return JSONResponse({"ok": False, "error": "读取原配置失败，请刷新后重试"}, status_code=400)
        base = detail["data"]

    try:
        row = cfgmodel.build_row(channel, fields, base)
    except Exception as exc:
        return JSONResponse({"ok": False, "error": f"配置合成失败：{exc}"}, status_code=400)

    # 官方客户端的写法是 FlushCfgRow(["upsert", row])：带 id 就是改，不带 id 就是新增，
    # 返回值 {"task_id": N} 即落库后的行号。（试过 "add"/"update"，后端不认。）
    if mode == "update":
        row["id"] = int(str(form.get("id") or 0))
    else:
        row.pop("id", None)

    result = await backend.call(channel, "FlushCfgRow", ["upsert", row])
    if result.get("errors"):
        return JSONResponse(
            {
                "ok": False,
                "error": "后端拒绝了这条配置",
                "detail": result.get("errors"),
                "sent": row,
            },
            status_code=400,
        )
    data = result.get("data")
    new_id = data.get("task_id") if isinstance(data, dict) else None
    log.info("cfg save user=%s %s id=%s title=%r", session.user, channel, new_id, row.get("title"))
    return JSONResponse({"ok": True, "mode": mode, "id": new_id, "row": row, "result": result})


@app.post("/api/cfg/rows")
async def api_cfg_rows(request: Request, session: Session = Depends(guard)):
    """对选中的配置行批量执行 StartCfgRows / StopCfgRows / RmCfgRows / Clear*His。"""
    form = await request.form()
    if not auth.check_csrf(session, str(form.get("csrf_token", ""))):
        return JSONResponse({"ok": False, "error": "csrf"}, status_code=400)
    channel = str(form.get("channel", ""))
    action = str(form.get("action", ""))
    raw = str(form.get("ids", ""))
    if channel not in parity.BY_KEY:
        return JSONResponse({"ok": False, "error": "unknown channel"}, status_code=400)
    if action not in parity.BY_KEY[channel].actions:
        return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
    try:
        ids = [int(x) for x in raw.replace("，", ",").split(",") if x.strip()]
    except ValueError:
        return JSONResponse({"ok": False, "error": "ids 必须是逗号分隔的整数"}, status_code=400)
    if not ids:
        return JSONResponse({"ok": False, "error": "没有选中任何配置行"}, status_code=400)

    # StartCfgRows / StopCfgRows / RmCfgRows 都是「id 列表」入参，直接转给后端即可
    result = await backend.call(channel, action, ids)
    log.info("cfg rows user=%s %s.%s ids=%r ok=%s", session.user, channel, action, ids, result["ok"])
    return JSONResponse(result)


# ------------------------------------------------------------------ 诊断


@app.get("/api/diag")
async def api_diag(session: Session = Depends(guard)):
    """把最容易把容器搞挂的两个文件直接读出来看。"""
    info: dict[str, Any] = {"ok": True, "app_dir": str(APP_DIR)}

    def _read(name: str) -> Any:
        path = APP_DIR / name
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return None
        except Exception as exc:
            return f"<读取失败: {exc}>"

    info["host_cfg"] = _read("host-cfg.json")
    info["ui_cfg"] = _read("ui-cfg.yml")
    info["ui_proxy"] = _read("ui-proxy.yml")
    info["sys"] = _read("sys")
    info["backend_ok"] = await backend.ping(timeout=2.0)
    syslog = backend.syslog_path()
    info["syslog"] = str(syslog) if syslog else None
    info["syslog_tail"] = backend.tail(syslog, 4000) if syslog else ""
    errlog = backend._newest_errlog()
    info["errlog"] = str(errlog) if errlog else None
    info["errlog_tail"] = backend.tail(errlog, 4000) if errlog else ""

    warnings: list[str] = []
    try:
        host = json.loads(info["host_cfg"] or "{}")
        if not (0 < int(host.get("http_port") or 0) < 65536):
            warnings.append("host-cfg.json 的 http_port 不是有效端口，后端会启动失败（应为 3334）")
        if not (0 < int(host.get("ws_port") or 0) < 65536):
            warnings.append("host-cfg.json 的 ws_port 不是有效端口（应为 3333）")
    except Exception:
        warnings.append("host-cfg.json 不是合法 JSON")
    info["warnings"] = warnings
    return JSONResponse(info)


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
