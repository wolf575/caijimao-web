"""后端动作的 payload 规格（4.3.0）。

来源：
1. 官方桌面客户端的 ``utils/http_req*.pyc``（6 个模块、136 个调用点）反汇编结果
   —— ``work/caijimao430/payloads_ui.json``；
2. 后端自身的 serde 报错信息（``app/logs/err.*.log``），例如
   ``invalid type: integer `1`, expected a boolean``。

**这是本项目最容易被忽略的一层**：HTTP 通道对任何 action 都回 ``ok``，
payload 形状不对时只会往 err.log 写一行 ``deserialize_err``，
所以在网页上表现为「点了没反应」或「后端错误」。
本模块把每个 action 的值类型固定下来，前端表单只需按类型收集。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# kind 取值：
#   unit    -> 1（后端用 serde 的 unit 变体，任何非 null 的标量都会被拒，1 是桌面端习惯用法）
#   int     -> 整数
#   bool    -> true / false
#   str     -> 字符串
#   list    -> 列表（元素类型见 elem）
#   tuple2  -> 二元组 [a, b]
#   obj     -> 结构体，字段见 fields
#   raw     -> 原样 JSON（结构复杂、由桌面端动态拼装的动作）

Spec = Dict[str, Any]


def _unit() -> Spec:
    return {"kind": "unit", "hint": "无参数（发送 1）"}


def _int(field: str = "value", hint: str = "") -> Spec:
    return {"kind": "int", "field": field, "hint": hint or f"整数：{field}"}


def _bool(field: str = "value", hint: str = "") -> Spec:
    return {"kind": "bool", "field": field, "hint": hint or f"布尔：{field}"}


def _str(field: str = "value", hint: str = "") -> Spec:
    return {"kind": "str", "field": field, "hint": hint or f"文本：{field}"}


def _list(elem: str = "int", field: str = "value", hint: str = "") -> Spec:
    return {"kind": "list", "elem": elem, "field": field, "hint": hint or f"列表（元素 {elem}）"}


def _tuple2(a: str, b: str, hint: str = "") -> Spec:
    return {"kind": "tuple2", "fields": (a, b), "hint": hint or f"两个值：[{a}, {b}]"}


def _obj(fields: Tuple[str, ...], hint: str = "") -> Spec:
    return {"kind": "obj", "fields": fields, "hint": hint or "对象：" + ", ".join(fields)}


def _raw(hint: str = "复杂结构，请按桌面版格式填写 JSON") -> Spec:
    return {"kind": "raw", "hint": hint}


# --------------------------------------------------------------------------
# 精确规格：登录 / 设置 / 配置行 / 服务控制 / 备份恢复 —— 网页上真正会用到的部分
# --------------------------------------------------------------------------
SPEC: Dict[Tuple[str, str], Spec] = {
    # ---- td_web_req：登录与全局设置 ----
    ("td_web_req", "SendPhone"): _str("phone", "手机号，含国际区号，例如 +8613800138000"),
    ("td_web_req", "SendAuthCode"): _str("code", "Telegram 发来的验证码"),
    ("td_web_req", "SendPassword"): _str("password", "两步验证密码（未开启可留空跳过）"),
    ("td_web_req", "NotifyMyChats"): _bool("enabled", "是否刷新会话列表"),
    ("td_web_req", "JoinChat"): _str("url", "群/频道链接，例如 https://t.me/xxx"),
    ("td_web_req", "JoinChatOfMsgLink"): _str("url", "消息链接，例如 https://t.me/xxx/123"),
    ("td_web_req", "ToMyChatsOtherOfMsgLink"): _str("url", "消息链接"),
    ("td_web_req", "MsgUrl"): _str("url", "消息链接"),
    ("td_web_req", "BatchExitChat"): _list("int", "cids", "要退出的会话 id 列表"),
    # 官方客户端把整个代理数组发过来（arg(data)），不是 bool。落盘到 ui-proxy.yml 只是顺带。
    ("td_web_req", "FlushUiProxies"): _list("obj", "proxies", "代理列表，元素含 enabled/server/port/user_name/password/secret/tp"),
    # 这两个都是 bool 入参；漏掉就会变成整数 1 → err.log 里 "expected a boolean"
    ("td_web_req", "GetMyChatsFull"): _bool("enabled", "是否拉取完整会话列表（含频道/群）"),
    ("td_web_req", "StopProg"): _bool("enabled", "停止后台服务（会让后端退出，随后自动重启）"),
    ("td_web_req", "FlushAntConfig"): _obj(
        ("api_id", "api_hash", "req_limit", "phone", "hide_phone", "proxy"),
        "TDLib 参数；req_limit 必须 ≥ 1，phone 留空或写 +86…",
    ),
    ("td_web_req", "FlushHostCfg"): _obj(
        ("http_port", "ws_port", "name"),
        "网页后端端口；http_port 默认 3334、ws_port 默认 3333，写 0 会导致后端启动后无法监听！",
    ),
    ("td_web_req", "FlushFileNameReplaces"): _obj(("replaces", "debug"), "文件名替换规则"),
    ("td_web_req", "SetHdPwd"): _tuple2("old_hd", "raw_pwd", "客户保护密码：[旧客户id, 新密码]"),
    ("td_web_req", "UpgradeHd"): _tuple2("old_hd", "raw_pwd", "授权迁移：[旧客户id, 密码]"),
    ("td_web_req", "FlushEncoder"): _str("encoder", "编码器名，例如 libx264"),
    ("td_web_req", "FlushFFMpegThreadCount"): _int("threads", "ffmpeg 线程数"),
    ("td_web_req", "FlushFFMpegSpeedDecode"): _bool("enabled", "是否开启快速解码"),
    ("td_web_req", "FlushSqliteSyncOff"): _bool("enabled", "是否关闭 sqlite 同步（提高速度、降低安全性）"),
    ("td_web_req", "DispatchUrlMarkDown"): _raw("Markdown 分发参数"),
    # ---- 五个服务通道的通用动作 ----
    ("ecr_td_web_req", "GetCfgRow"): _int("task_id", "配置行 id"),
    ("ecr_td_web_req", "GetTaskStats"): _int("task_id", "配置行 id"),
    ("ecr_td_web_req", "FlushCfgRow"): _tuple2("action", "data", '["add"|"update", 配置行对象]'),
    ("ecr_td_web_req", "StartCfgRows"): _list("int", "ids", "要启动的配置行 id 列表"),
    ("ecr_td_web_req", "StopCfgRows"): _list("int", "ids", "要停止的配置行 id 列表"),
    ("ecr_td_web_req", "RmCfgRows"): _list("int", "ids", "要删除的配置行 id 列表"),
    ("ecr_td_web_req", "ClearCrawHis"): _list("int", "ids", "要清理爬取历史的配置行 id 列表"),
    ("ecr_td_web_req", "ClearSendHis"): _list("int", "ids", "要清理发送历史的配置行 id 列表"),
    ("ecr_td_web_req", "SetCrawTo"): _str("url", "从消息链接反查会话"),
    ("ecr_td_web_req", "GetThreadId"): _str("url", "消息链接"),
    ("ecr_td_web_req", "GetMessageId"): _str("url", "消息链接"),
    ("ecr_td_web_req", "GetMessageUser"): _str("url", "消息链接"),
    ("ecr_td_web_req", "RestoreCfg"): _str("file_name", "备份文件名"),
    ("ecr_td_web_req", "RegexReplace"): _raw("正则替换测试参数"),
    ("ecr_td_web_req", "TestReplaceBatch"): _raw("批量替换测试参数"),
    ("ecr_td_web_req", "TestMarkdown"): _str("body", "要渲染的 Markdown 文本"),
    ("ecr_td_web_req", "SendMessage"): _raw("发送消息参数"),
    ("ecc_td_web_req", "GetCfgRow"): _int("task_id", "配置行 id"),
    ("ecc_td_web_req", "GetTaskStats"): _int("task_id", "配置行 id"),
    ("ecc_td_web_req", "FlushCfgRow"): _tuple2("action", "data", '["add"|"update", 配置行对象]'),
    ("ecc_td_web_req", "StartCfgRows"): _list("int", "ids", "配置行 id 列表"),
    ("ecc_td_web_req", "StopCfgRows"): _list("int", "ids", "配置行 id 列表"),
    ("ecc_td_web_req", "RmCfgRows"): _list("int", "ids", "配置行 id 列表"),
    ("ecc_td_web_req", "ClearTaskProgress"): _list("int", "ids", "配置行 id 列表"),
    ("ecc_td_web_req", "BatchClearTaskProgress"): _list("int", "ids", "配置行 id 列表"),
    ("ecc_td_web_req", "SetCrawTo"): _str("url", "消息链接"),
    ("ecc_td_web_req", "SetMultiMainCrawTo"): _raw("多主群设置参数"),
    ("ecc_td_web_req", "SetCrawToBatch"): _raw("批量设置参数"),
    ("ecc_td_web_req", "GetThreadId"): _str("url", "消息链接"),
    ("ecc_td_web_req", "SmartGetThreadId"): _str("url", "消息链接"),
    ("ecc_td_web_req", "GetMessageId"): _str("url", "消息链接"),
    ("ecc_td_web_req", "GetMessageUser"): _str("url", "消息链接"),
    ("ecc_td_web_req", "GetMessageSender"): _str("url", "消息链接"),
    ("ecc_td_web_req", "RestoreCfg"): _str("file_name", "备份文件名"),
    ("ecc_td_web_req", "SendMessage"): _raw("发送消息参数"),
    ("ecc_td_web_req", "TestMarkdown"): _str("body", "Markdown 文本"),
    ("va_td_web_req", "GetCfgRow"): _int("task_id", "配置行 id"),
    ("va_td_web_req", "GetTaskStats"): _int("task_id", "配置行 id"),
    ("va_td_web_req", "FlushCfgRow"): _tuple2("action", "data", '["add"|"update", 配置行对象]'),
    ("va_td_web_req", "StartCfgRows"): _list("int", "ids", "配置行 id 列表"),
    ("va_td_web_req", "StopCfgRows"): _list("int", "ids", "配置行 id 列表"),
    ("va_td_web_req", "RmCfgRows"): _list("int", "ids", "配置行 id 列表"),
    ("va_td_web_req", "RestoreCfg"): _str("file_name", "备份文件名"),
    ("va_td_web_req", "FreeDownloadUrl"): _str("url", "消息链接"),
    ("va_td_web_req", "ExportMd5"): _obj(("is_task", "x_id", "short_dir"), "导出 md5 参数"),
    ("va_td_web_req", "MoveSrcDirs"): _obj(("src_dir_short", "dst_dir_short", "del_src"), "移动源目录"),
    ("va_td_web_req", "GetMsgLocalDir"): _str("url", "消息链接"),
    ("va_td_web_req", "ImportFiles"): _raw("导入文件参数"),
    ("va_td_web_req", "DelChatMd5"): _raw("删除会话 md5 参数"),
    ("replace_td_web_req", "ClearCrawHis"): _list("int", "ids", "配置行 id 列表"),
    ("replace_td_web_req", "ClearReplaceHis"): _list("int", "ids", "配置行 id 列表"),
    ("replace_td_web_req", "RestoreCfg"): _str("file_name", "备份文件名"),
    ("button_bot_web_req", "RestoreCfg"): _str("file_name", "备份文件名"),
}


def spec_of(channel: str, action: str) -> Spec:
    """返回某个动作的 payload 规格；未登记的默认按 unit(1) 处理（桌面端多数如此）。"""
    return SPEC.get((channel, action)) or _unit()


def kind_of(channel: str, action: str) -> str:
    return spec_of(channel, action)["kind"]


def describe(channel: str, action: str) -> str:
    return spec_of(channel, action).get("hint", "")


def _as_int(v: Any) -> int:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s == "":
        raise ValueError("需要一个整数，但收到空值")
    return int(s)


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on", "y"):
        return True
    if s in ("0", "false", "no", "off", "n", ""):
        return False
    raise ValueError(f"需要一个布尔值（true/false），但收到 {v!r}")


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        raise ValueError("需要一个字符串，但收到 JSON 结构")
    return str(v)


def _as_list(v: Any, elem: str) -> List[Any]:
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return []
        if s.startswith("["):
            import json

            v = json.loads(s)
        else:
            v = [x for x in (p.strip() for p in s.replace("，", ",").split(",")) if x != ""]
    if not isinstance(v, list):
        raise ValueError("需要一个列表")
    if elem == "int":
        return [_as_int(x) for x in v]
    return v


def build(channel: str, action: str, form: Dict[str, Any]) -> Any:
    """把网页表单字段转换成后端要求的 payload 值。

    ``form`` 是 ``{字段名: 原始字符串}``；字段名来自 :func:`spec_of`。
    """
    import json

    sp = spec_of(channel, action)
    kind = sp["kind"]

    if kind == "unit":
        return 1
    if kind == "int":
        return _as_int(form.get(sp.get("field", "value"), 1))
    if kind == "bool":
        return _as_bool(form.get(sp.get("field", "value"), True))
    if kind == "str":
        return _as_str(form.get(sp.get("field", "value"), ""))
    if kind == "list":
        return _as_list(form.get(sp.get("field", "value"), []), sp.get("elem", "int"))
    if kind == "tuple2":
        out = []
        for name in sp["fields"]:
            raw = form.get(name, "")
            if isinstance(raw, str) and raw.strip().startswith(("[", "{")):
                out.append(json.loads(raw))
            else:
                out.append(raw)
        return out
    if kind == "obj":
        obj: Dict[str, Any] = {}
        for name in sp["fields"]:
            if name in form:
                obj[name] = form[name]
        return obj
    # raw
    raw = form.get("value", form.get("raw", "1"))
    if isinstance(raw, (dict, list)):
        return raw
    s = str(raw).strip()
    if s == "":
        return 1
    try:
        return json.loads(s)
    except Exception:
        return s
