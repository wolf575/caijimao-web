"""把配置行模板/现有行自动展开成「可编辑字段表」，并支持把表单值写回。

这样就不用为 ecr / ecc / va / replace / btnbot 每个通道手写 60+ 个输入框：
结构、枚举、默认值都来自后端真实数据，网页只负责渲染和回填。

字段路径用点号表示，例如 `data.Craw.from_chat.cid`。
"""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, Iterable, List, Tuple

# 值需要用户手填 JSON 的复杂结构（列表里放对象），其它 list 都能用文本表达
_JSON_LIST_KEYS = {"crons", "replaces", "senders", "buttons", "tran_msg_image_url",
                   "slow_chats", "filter_topic", "slave", "del_keywords"}

_ENUMS: Dict[str, List[str]] = {
    "ruler_action": ["craw", "now", "download", "lib", "Single", "Discuss", "Topic",
                     "vip", "preview", "rand", "param"],
    "tp": ["url", "date"],
    "slice_type": ["EachVideo", "AllVideo"],
    "pos": ["top", "bottom", "top-move", "bottom-move"],
    "filter_text_type": ["All", "Text", "Media"],
    "action": ["Del", "Replace"],
}

# 中文标签（按最后一段 key），没有就用原 key
_LABELS: Dict[str, str] = {
    "title": "标题", "prior_no": "优先级", "is_start": "启用", "ruler_action": "规则类型",
    "craw_types": "爬取消息类型", "restrict_craw_type": "仅爬指定类型",
    "from_chat": "来源", "to_chat": "目标", "to_chats": "目标(多个)",
    "cid": "chat id", "tid": "话题 id", "url": "链接", "remark": "备注",
    "is_channel": "是频道", "start": "起点", "end": "终点", "date": "日期",
    "always_download": "总是下载", "replaces": "替换规则", "gt_size": "大于字节",
    "lt_size": "小于字节", "gt_minutes": "时长大于(分)", "lt_minutes": "时长小于(分)",
    "gt_wh": "分辨率大于", "lt_wh": "分辨率小于", "exclude_keywords": "排除关键词",
    "include_keywords": "包含关键词", "offset_minutes": "起点偏移(分)",
    "offset_minutes_end": "终点偏移(分)", "no_send_empty_caption_msg": "空文案不发送",
    "optimize_len": "优化时长", "add_foot_print_video": "视频加水印",
    "add_foot_print_image": "图片加水印", "foot_print": "水印", "font_path": "字体文件",
    "font_name": "字体名", "font_size": "字号", "auto_font_size": "自动字号",
    "font_color": "字体颜色", "thread_count": "线程数",
    "adjust_video_cover": "调整视频封面", "always_preview": "总是预览",
    "tran_msg_to_text": "消息转文本", "tran_msg_image_url": "转图片链接",
    "video_slice": "视频切片", "video_slice_data": "切片参数",
    "optimize_md5": "改 MD5", "crop_video": "裁剪视频", "crop_image": "裁剪图片",
    "crop_data": "裁剪参数", "mirror_video": "镜像视频", "mirror_image": "镜像图片",
    "pad_video": "补边视频", "pad_image": "补边图片", "pad_data": "补边参数",
    "virtual_duration": "虚拟时长", "virtual_duration_data": "虚拟时长参数",
    "offset_min": "偏移最小", "offset_max": "偏移最大", "color": "颜色",
    "to_video_len": "切片时长", "to_video_len1": "切片时长2",
    "to_video_count": "切片数量", "to_video_count1": "切片数量2",
    "new_cover": "新封面", "cron_apply": "启用定时", "crons": "定时计划",
    "filter_sender": "发送者过滤", "is_anonymous": "匿名管理员", "is_admin": "管理员",
    "is_bot": "机器人", "senders": "指定发送者", "is_all": "全部", "is_sel": "仅选中",
    "slave": "从属", "filter_topic": "话题过滤", "send_pre_msg": "先发提示",
    "pre_msg_be_markdown": "提示用 Markdown", "pre_msg_content": "提示内容",
    "force_2_discuss_or_topic": "强制转讨论/话题", "monitor_now_msg": "只看新消息",
    "del_keywords": "删除关键词", "no_right_del": "无权限也删",
    "src_tps": "来源类型", "sender_tps": "发送者类型", "split_album": "拆分相册",
    "from_cids": "来源(多个)", "to_cids": "目标(多个)", "row_button_count": "按钮行数",
    "buttons": "按钮", "token": "机器人 token", "speed_limit": "速度限制",
    "show_detail_log": "详细日志", "slow_chats": "慢速聊天",
    "from_cid": "来源 chat", "msg_his": "历史消息",
}


def label_of(path: str) -> str:
    key = path.rsplit(".", 1)[-1]
    return _LABELS.get(key, key)


# 空列表时靠 key 猜类型，否则空 [] 会被当成 JSON 框
_LIST_HINT: Dict[str, str] = {
    "craw_types": "ints", "gt_wh": "ints", "lt_wh": "ints",
    "from_cids": "ints", "to_cids": "ints", "src_tps": "ints", "sender_tps": "ints",
    "exclude_keywords": "lines", "include_keywords": "lines", "del_keywords": "lines",
    "tran_msg_image_url": "lines",
    "replaces": "json", "crons": "json", "buttons": "json", "senders": "json",
    "slow_chats": "json", "filter_topic": "json", "slave": "json", "msg_his": "json",
}


def _kind_of(value: Any, key: str) -> str:
    if key in _ENUMS:
        return "enum"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        if key in _JSON_LIST_KEYS:
            return "json"
        if value and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in value):
            return "ints"
        if value and all(isinstance(x, str) for x in value):
            return "lines"
        return _LIST_HINT.get(key, "json")
    return "json"


def schema(sample: Any, prefix: str = "", depth: int = 0) -> List[Dict[str, Any]]:
    """把样例（模板或现有行）展开成字段列表。dict 递归，其它叶子各成一个字段。"""
    out: List[Dict[str, Any]] = []
    if isinstance(sample, dict):
        for k, v in sample.items():
            if k == "id":
                continue
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                out.extend(schema(v, path, depth + 1))
            else:
                kind = _kind_of(v, k)
                item = {
                    "path": path,
                    "label": label_of(path),
                    "kind": kind,
                    "value": v,
                    "group": prefix.split(".")[0] if prefix else "",
                }
                if kind == "enum":
                    opts = list(_ENUMS[k])
                    if v not in opts and v != "":
                        opts.insert(0, v)
                    item["options"] = opts
                out.append(item)
    return out


def groups(sample: Any) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """按顶层分组，方便页面用 <details> 折叠。"""
    fields = schema(sample)
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for f in fields:
        top = f["path"].split(".")[0]
        buckets.setdefault(top, []).append(f)
    return [(k, v) for k, v in buckets.items()]


def _coerce(raw: str, ref: Any, kind: str) -> Any:
    if kind == "bool":
        return raw in ("1", "true", "True", "on", "yes")
    if kind == "number":
        try:
            return int(raw)
        except ValueError:
            try:
                return float(raw)
            except ValueError:
                return ref if ref is not None else 0
    if kind == "ints":
        out = []
        for part in str(raw).replace("，", ",").split(","):
            part = part.strip()
            if part:
                try:
                    out.append(int(part))
                except ValueError:
                    pass
        return out
    if kind == "lines":
        return [ln.strip() for ln in str(raw).splitlines() if ln.strip()]
    if kind == "json":
        try:
            return json.loads(raw) if str(raw).strip() else (ref if ref is not None else None)
        except json.JSONDecodeError:
            raise ValueError(f"JSON 解析失败：{raw[:60]}")
    return raw


def _set_path(node: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = node
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return
        cur = cur[p]
    if isinstance(cur, dict):
        cur[parts[-1]] = value


def _get_path(node: Any, path: str) -> Any:
    cur = node
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def apply_fields(sample: Any, fields: Dict[str, str]) -> Any:
    """把 {路径: 原始字符串} 写进样例的深拷贝里。只处理 schema 里存在的路径。"""
    out = copy.deepcopy(sample)
    known = {f["path"]: f for f in schema(sample)}
    for path, raw in fields.items():
        f = known.get(path)
        if not f:
            continue
        ref = _get_path(sample, path)
        _set_path(out, path, _coerce(raw, ref, f["kind"]))
    return out


def describe(sample: Any) -> List[Dict[str, Any]]:
    """给前端用：把 groups 摊平成 [{group, label, fields}]。"""
    return [{"group": g, "label": label_of(g), "fields": fs} for g, fs in groups(sample)]
