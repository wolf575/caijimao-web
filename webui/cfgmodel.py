"""各服务通道的配置模型：字段表 + 行模板 + 表单合成。

「新增配置」不是凭空造的：ecr / ecc 的模板直接取自官方桌面版真实配置行
（``webui/cfg_templates/*.json``，由 ``work/caijimao430/dump_rows.py`` 导出），
网页表单只覆盖最常用的少数字段，其余字段原样保留，
因此提交给后端 ``FlushCfgRow`` 的结构与桌面版完全一致。
"""
from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(HERE, "cfg_templates")

# 每个通道：配置在 GetCfg 返回里的键名、行列表键名、规则类型取值、是否有 FlushCfgRow
CHANNEL_MODEL: Dict[str, Dict[str, Any]] = {
    "ecr_td_web_req": {
        "label": "爬虫PRO",
        "list_key": "rulers",
        "actions": ["craw", "now", "download", "lib"],
        "action_labels": {
            "craw": "爬取（按区间抓取并转发）",
            "now": "即时（从当前消息开始）",
            "download": "仅下载",
            "lib": "媒体库",
        },
        "row_api": True,
        "template": "ecr.json",
        "from_key": "data.Craw.from_chat",
        "to_key": "data.Craw.to_chat",
        "start_key": "data.Craw.start",
        "end_key": "data.Craw.end",
    },
    "ecc_td_web_req": {
        "label": "频道群克隆PRO",
        "list_key": "tasks",
        "actions": ["Single", "Discuss", "Topic"],
        "action_labels": {
            "Single": "单群克隆",
            "Discuss": "评论区克隆",
            "Topic": "话题克隆",
        },
        "row_api": True,
        "template": "ecc.json",
        "from_key": "data.from_chat",
        "to_key": "data.to_chat",
        "start_key": "data.start",
        "end_key": "data.end",
    },
    "va_td_web_req": {
        "label": "付费群助手",
        "list_key": "rulers",
        "actions": ["vip", "craw", "preview", "rand", "param"],
        "action_labels": {
            "vip": "VIP 频道搬运",
            "craw": "爬取",
            "preview": "预览",
            "rand": "随机",
            "param": "参数",
        },
        "row_api": True,
        "template": "va.json",
        "from_key": "data.from_chat",
        "to_key": "data.to_chat",
        "start_key": "data.start",
        "end_key": "data.end",
    },
    "replace_td_web_req": {
        "label": "批量替换/删除",
        "list_key": "rulers",
        "actions": [],
        "action_labels": {},
        "row_api": False,
        "whole": True,
        "template": "replace.json",
        "from_key": None,
        "to_key": None,
        "start_key": None,
        "end_key": None,
    },
    "button_bot_web_req": {
        "label": "按钮机器人",
        "list_key": "rulers",
        "actions": [],
        "action_labels": {},
        "row_api": False,
        "whole": True,
        "template": "btnbot.json",
        "from_key": None,
        "to_key": None,
        "start_key": None,
        "end_key": None,
    },
}


def _get(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set(obj: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = obj
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def model(channel: str) -> Dict[str, Any]:
    return CHANNEL_MODEL.get(channel, {})


def list_key(channel: str) -> str:
    return model(channel).get("list_key", "rulers")


def has_row_api(channel: str) -> bool:
    return bool(model(channel).get("row_api"))


def template(channel: str) -> Optional[Dict[str, Any]]:
    name = model(channel).get("template")
    if not name:
        return None
    path = os.path.join(TPL_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _int_or(value: Any, default: int = 0) -> int:
    try:
        s = str(value).strip()
        if s == "":
            return default
        return int(s)
    except Exception:
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _chat(cid: Any, title: str, is_channel: bool = True) -> Dict[str, Any]:
    return {"cid": _int_or(cid), "title": (title or "").strip(), "is_channel": bool(is_channel)}


def build_row(channel: str, form: Dict[str, Any], base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把网页表单合成一行完整配置。

    ``base`` 用于「编辑」：传入从后端取回的原始行，保留用户没在表单里改的字段。
    """
    m = model(channel)
    if base is not None:
        row = copy.deepcopy(base)
    else:
        tpl = template(channel)
        if tpl is None:
            raise ValueError(f"{channel} 没有可用的配置模板")
        row = copy.deepcopy(tpl)

    if form.get("title") is not None:
        row["title"] = str(form.get("title") or "").strip()
    if form.get("ruler_action"):
        row["ruler_action"] = str(form["ruler_action"])
    if "is_start" in form:
        row["is_start"] = _bool(form.get("is_start"))
    if form.get("prior_no") not in (None, ""):
        row["prior_no"] = _int_or(form.get("prior_no"), 1)

    from_key, to_key = m.get("from_key"), m.get("to_key")
    if from_key and (form.get("from_cid") not in (None, "")):
        _set(row, from_key, _chat(form.get("from_cid"), form.get("from_title", ""), True))
    if to_key and (form.get("to_cid") not in (None, "")):
        _set(row, to_key, _chat(form.get("to_cid"), form.get("to_title", ""), True))

    start_key, end_key = m.get("start_key"), m.get("end_key")
    if start_key:
        start = _get(row, start_key) or {}
        tp = form.get("start_tp") or start.get("tp") or "url"
        start["tp"] = tp
        if tp == "url":
            if form.get("start_url") not in (None, ""):
                start["url"] = str(form.get("start_url")).strip()
        else:
            if form.get("start_date") not in (None, ""):
                start["date"] = _int_or(form.get("start_date"))
        _set(row, start_key, start)
    if end_key:
        end = _get(row, end_key) or {}
        tp = form.get("end_tp") or end.get("tp") or "url"
        end["tp"] = tp
        if tp == "url":
            if form.get("end_url") not in (None, ""):
                end["url"] = str(form.get("end_url")).strip()
        else:
            if form.get("end_date") not in (None, ""):
                end["date"] = _int_or(form.get("end_date"))
        _set(row, end_key, end)

    kws = form.get("exclude_keywords")
    if kws not in (None, ""):
        parts = [p.strip() for p in str(kws).replace("，", ",").split(",") if p.strip()]
        holder = _get(row, "data.Craw") if channel == "ecr_td_web_req" else _get(row, "data")
        if isinstance(holder, dict):
            holder["exclude_keywords"] = parts

    override = form.get("json_override")
    if override not in (None, ""):
        row = json.loads(override)

    row.pop("id", None) if base is None else None
    return row


def brief(row: Dict[str, Any], channel: str) -> Dict[str, Any]:
    """给列表用的精简视图。"""
    m = model(channel)
    frm = _get(row, m.get("from_key") or "") or {}
    to = _get(row, m.get("to_key") or "") or {}
    start = _get(row, m.get("start_key") or "") or {}
    end = _get(row, m.get("end_key") or "") or {}
    return {
        "id": row.get("id"),
        "title": row.get("title", ""),
        "ruler_action": row.get("ruler_action", ""),
        "is_start": bool(row.get("is_start")),
        "prior_no": row.get("prior_no"),
        "from": f"{frm.get('title') or ''} ({frm.get('cid')})" if frm else "",
        "to": f"{to.get('title') or ''} ({to.get('cid')})" if to else "",
        "start": start.get("url") or start.get("date") or "",
        "end": end.get("url") or end.get("date") or "",
    }


def is_whole(channel: str) -> bool:
    """replace_td / button_bot 没有 FlushCfgRow，只能整份配置 FlushCfg。"""
    return bool(CHANNEL_MODEL.get(channel, {}).get("whole"))


def whole_config(channel: str) -> Optional[Dict[str, Any]]:
    """整份配置的模板（含一条示例行），用于「初始化配置」。"""
    model = CHANNEL_MODEL.get(channel) or {}
    name = model.get("template")
    if not name:
        return None
    path = os.path.join(TPL_DIR, name)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None
