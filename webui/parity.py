"""Single source of truth for the backend contract.

Every channel / action below was extracted from the shipped Rust backend
(`app\\crawler2.exe`) by triggering its serde "unknown variant" errors, so the
lists are authoritative, not guesses.

`page` on an action is the Web route that exposes it.  An action with
page=None is only reachable from /admin/console.  `selfcheck()` asserts that
every action has *some* entry point, which is what makes "1:1 feature parity"
a testable invariant instead of a promise.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Channel:
    key: str
    label: str
    ws_bus: str
    default_page: str | None
    actions: tuple[str, ...]
    overrides: dict[str, str | None] = field(default_factory=dict)

    def page_for(self, action: str) -> str | None:
        if action in self.overrides:
            return self.overrides[action]
        return self.default_page


TD = Channel(
    key="td_web_req",
    label="TD 全局 / 登录",
    ws_bus="td_login_ws_bus",
    default_page="/settings",
    actions=(
        "None",
        "GetFileNameReplaces",
        "FlushFileNameReplaces",
        "FlushHostCfg",
        "GetHostCfg",
        "MsgUrl",
        "DispatchUrlMarkDown",
        "GetMyChatsFull",
        "NotifyMyChats",
        "DoLogin",
        "DoLogout",
        "StopProg",
        "SendPhone",
        "SendAuthCode",
        "SendPassword",
        "ReloadCfg",
        "FlushUiProxies",
        "FlushAntConfig",
        "GetAntConfig",
        "GetHD",
        "GetVersion",
        "GetLease",
        "SetHdPwd",
        "UpgradeHd",
        "BatchExitChat",
        "JoinChat",
        "JoinChatOfMsgLink",
        "ToMyChatsOtherOfMsgLink",
        "FlushEncoder",
        "FlushFFMpegThreadCount",
        "FlushFFMpegSpeedDecode",
        "TestFootPrint",
        "StopTestFootPrint",
        "GetEncoder",
        "GetFFMpegThreadCount",
        "GetFFMpegSpeedDecode",
        "GetSqliteSyncOff",
        "FlushSqliteSyncOff",
    ),
    overrides={
        "GetHD": "/",
        "GetVersion": "/",
        "GetLease": "/",
        "GetMyChatsFull": "/td-login",
        "NotifyMyChats": "/td-login",
        "DoLogin": "/td-login",
        "DoLogout": "/td-login",
        "SendPhone": "/td-login",
        "SendAuthCode": "/td-login",
        "SendPassword": "/td-login",
        "BatchExitChat": "/td-login",
        "JoinChat": "/td-login",
        "JoinChatOfMsgLink": "/td-login",
        "ToMyChatsOtherOfMsgLink": "/td-login",
        "MsgUrl": "/ecr",
        "DispatchUrlMarkDown": "/ecr",
        "None": None,
    },
)

ECR = Channel(
    key="ecr_td_web_req",
    label="爬虫PRO",
    ws_bus="ecr_td_ws_bus",
    default_page="/ecr",
    actions=(
        "Ping",
        "ClearTaskProgress",
        "BatchClearTaskProgress",
        "SetCrawTo",
        "ClearSendHis",
        "GetCfg",
        "FlushCfg",
        "GetThreadId",
        "GetMessageId",
        "GetMessageUser",
        "GetBackupFiles",
        "RestoreCfg",
        "StopServiceOnlyCraw",
        "StopService",
        "StartService",
        "GetTaskStats",
        "RegexReplace",
        "TestReplaceBatch",
        "TestMarkdown",
        "SendMessage",
        "FlushCfgRow",
        "GetCfgRow",
        "RmCfgRows",
        "StartCfgRows",
        "StopCfgRows",
    ),
)

ECC = Channel(
    key="ecc_td_web_req",
    label="频道群克隆PRO",
    ws_bus="ecc_td_ws_bus",
    default_page="/ecc",
    actions=(
        "Ping",
        "ClearTaskProgress",
        "BatchClearTaskProgress",
        "SetCrawTo",
        "SetMultiMainCrawTo",
        "SetCrawToBatch",
        "GetCfg",
        "FlushCfg",
        "GetThreadId",
        "SmartGetThreadId",
        "GetMessageId",
        "GetMessageUser",
        "GetMessageSender",
        "GetBackupFiles",
        "RestoreCfg",
        "StopService",
        "StartService",
        "GetTaskStats",
        "GetTaskSyncProgress",
        "RegexReplace",
        "TestReplaceBatch",
        "TestMarkdown",
        "SendMessage",
        "FlushCfgRow",
        "GetCfgRow",
        "RmCfgRows",
        "StartCfgRows",
        "StopCfgRows",
    ),
)

REPLACE = Channel(
    key="replace_td_web_req",
    label="批量替换/删除服务",
    ws_bus="replace_td_ws_bus",
    default_page="/replace",
    actions=(
        "Ping",
        "ClearCrawHis",
        "ClearReplaceHis",
        "GetCfg",
        "FlushCfg",
        "GetBackupFiles",
        "RestoreCfg",
        "StopService",
        "StartService",
    ),
)

VA = Channel(
    key="va_td_web_req",
    label="付费群助手",
    ws_bus="va_td_ws_bus",
    default_page="/va",
    actions=(
        "Ping",
        "GetCfg",
        "FlushCfgRow",
        "GetCfgRow",
        "RmCfgRows",
        "StartCfgRows",
        "StopCfgRows",
        "FreeDownloadUrl",
        "FlushCfg",
        "GetThreadId",
        "GetMessageId",
        "GetMessageUser",
        "GetBackupFiles",
        "RestoreCfg",
        "StopService",
        "StartService",
        "GetTaskStats",
        "ImportFiles",
        "StopImportFiles",
        "ExportMd5",
        "DelChatMd5",
        "MoveSrcDirs",
        "ReBuildSrcDirs",
        "ClearTaskProgress",
        "BatchClearTaskProgress",
        "GetOptimizeSizeCfg",
        "FlushOptimizeSizeCfg",
        "GetSrcSubDirs",
        "GetMsgLocalDir",
        "GetAlLMd5Chats",
        "MsgRenewBatch",
    ),
)

BTN_BOT = Channel(
    key="button_bot_web_req",
    label="按钮机器人服务",
    ws_bus="button_bot_ws_bus",
    default_page="/btn-bot",
    actions=(
        "Ping",
        "GetCfg",
        "FlushCfg",
        "GetBackupFiles",
        "RestoreCfg",
        "StopBot",
        "StartBot",
    ),
)

CHANNELS: tuple[Channel, ...] = (TD, ECR, ECC, REPLACE, VA, BTN_BOT)

BY_KEY: dict[str, Channel] = {c.key: c for c in CHANNELS}

#: Every Web route that is allowed to appear as an action's `page`.
PAGES: tuple[str, ...] = (
    "/",
    "/td-login",
    "/ecr",
    "/replace",
    "/ecc",
    "/va",
    "/btn-bot",
    "/settings",
)

CONSOLE_PAGE = "/admin/console"


def total_actions() -> int:
    return sum(len(c.actions) for c in CHANNELS)


def console_only() -> list[tuple[str, str]]:
    """Actions that have no dedicated form and therefore must show up in the
    raw API console.  `/admin/console` renders exactly this list, so the
    console can never silently fall out of sync with the contract."""
    out: list[tuple[str, str]] = []
    for c in CHANNELS:
        for a in c.actions:
            if c.page_for(a) is None:
                out.append((c.key, a))
    return out


def selfcheck() -> list[str]:
    """Return a list of parity problems (empty == OK)."""
    problems: list[str] = []
    for c in CHANNELS:
        if not c.actions:
            problems.append(f"{c.key}: no actions")
        if c.default_page is not None and c.default_page not in PAGES:
            problems.append(f"{c.key}: unknown default_page {c.default_page}")
        for a, page in c.overrides.items():
            if a not in c.actions:
                problems.append(f"{c.key}: override for unknown action {a}")
            if page is not None and page not in PAGES:
                problems.append(f"{c.key}.{a}: unknown page {page}")
        for a in c.actions:
            page = c.page_for(a)
            if page is not None and page not in PAGES:
                problems.append(f"{c.key}.{a}: page {page} not implemented")
    seen: set[str] = set()
    for c in CHANNELS:
        if c.key in seen:
            problems.append(f"duplicate channel {c.key}")
        seen.add(c.key)
    return problems


def nav() -> list[dict[str, str]]:
    """Sidebar entries, ordered like the desktop tree."""
    return [
        {"href": "/", "label": "服务状态"},
        {"href": "/td-login", "label": "TD 登录"},
        {"href": "/ecr", "label": "爬虫PRO"},
        {"href": "/replace", "label": "批量替换/删除"},
        {"href": "/ecc", "label": "频道群克隆PRO"},
        {"href": "/va", "label": "付费群助手"},
        {"href": "/btn-bot", "label": "按钮机器人"},
        {"href": "/tools", "label": "工具"},
        {"href": "/settings", "label": "全局设置"},
        {"href": "/logs", "label": "日志"},
        {"href": CONSOLE_PAGE, "label": "API 控制台"},
    ]


if __name__ == "__main__":  # pragma: no cover - manual check
    errs = selfcheck()
    print(f"channels={len(CHANNELS)} actions={total_actions()}")
    print(f"console_only={len(console_only())}")
    for e in errs:
        print("PROBLEM:", e)
    print("OK" if not errs else "FAILED")


# ---------------------------------------------------------------------------
# 4.3.0 的 va_td_web_req 还有一批动作只出现在官方客户端的 http_req_va.pyc 里。
# err.log 里的 `expected one of ...` 文本被截断过，所以这里补回来（幂等）。
import dataclasses as _dc

_VA_EXTRA = (
    "SlowChatList", "FlushSlowChats",
    "DiscussLostChannel", "DiscussLostChannelData", "DiscussLostChannelDel",
    "DiscussLastLostChannel", "DiscussLastLostChannelData", "DiscussLastLostChannelDel",
    "DiscussLastLostChannelGen", "DiscussLastLostUrlReSync", "ManualDiscussProgress",
    "GetSendProgress", "SendContinue", "ClearCrawHis",
)
_va = BY_KEY["va_td_web_req"]
_missing = tuple(a for a in _VA_EXTRA if a not in _va.actions)
if _missing:
    _va2 = _dc.replace(_va, actions=_va.actions + _missing)
    BY_KEY["va_td_web_req"] = _va2
    CHANNELS = [c if c.key != _va2.key else _va2 for c in CHANNELS]
