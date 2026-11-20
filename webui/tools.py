"""工具页的动作清单。

只收录「有表单、网页上真能用」的动作；没收录的仍然可以在 /admin/console 里发。
字段类型来自 :mod:`webui.payloads` 的规格，所以这里只写分组与文案。
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import payloads

# (分组标题, 说明, [(channel, action, 标题, 说明)])
_GROUPS: List[Dict[str, Any]] = [
    {
        "title": "正则 / 替换测试",
        "desc": "桌面版「替换规则」里的测试按钮，先在这里确认正则匹配再启用规则。",
        "items": [
            ("ecr_td_web_req", "RegexReplace", "爬虫PRO · 正则替换测试", "tp 一般填 text 或 caption"),
            ("ecc_td_web_req", "RegexReplace", "克隆PRO · 正则替换测试", "同上"),
            ("ecr_td_web_req", "TestReplaceBatch", "爬虫PRO · 批量替换测试", "replaces 填替换规则数组"),
            ("ecc_td_web_req", "TestReplaceBatch", "克隆PRO · 批量替换测试", "同上"),
            ("ecr_td_web_req", "TestMarkdown", "爬虫PRO · Markdown 测试", ""),
            ("ecc_td_web_req", "TestMarkdown", "克隆PRO · Markdown 测试", ""),
        ],
    },
    {
        "title": "会话与消息",
        "desc": "加群、退群、按链接取会话信息，等同于桌面版右键菜单里的那些动作。",
        "items": [
            ("td_web_req", "JoinChat", "加入群 / 频道", "填 https://t.me/xxx"),
            ("td_web_req", "JoinChatOfMsgLink", "按消息链接加入", "填 https://t.me/xxx/123"),
            ("td_web_req", "ToMyChatsOtherOfMsgLink", "消息所在会话加入会话列表", ""),
            ("td_web_req", "MsgUrl", "解析消息链接", "返回 cid / msg_id"),
            ("td_web_req", "NotifyMyChats", "刷新会话列表", ""),
            ("td_web_req", "BatchExitChat", "批量退出会话", "cids 用逗号分隔"),
        ],
    },
    {
        "title": "取 id / 发送者",
        "desc": "桌面版「取 thread id / msg id / 发送者」的对应动作，配合配置行使用。",
        "items": [
            ("ecr_td_web_req", "GetThreadId", "爬虫PRO · 取 thread id", "填消息链接"),
            ("ecr_td_web_req", "GetMessageId", "爬虫PRO · 取 msg id", "填消息链接"),
            ("ecr_td_web_req", "GetMessageUser", "爬虫PRO · 取发送者", "填消息链接"),
            ("ecc_td_web_req", "GetThreadId", "克隆PRO · 取 thread id", "填消息链接"),
            ("ecc_td_web_req", "SmartGetThreadId", "克隆PRO · 智能取 thread id", "填消息链接"),
            ("ecc_td_web_req", "GetMessageId", "克隆PRO · 取 msg id", "填消息链接"),
            ("ecc_td_web_req", "GetMessageUser", "克隆PRO · 取发送者", "填消息链接"),
            ("ecc_td_web_req", "GetMessageSender", "克隆PRO · 取发送者(含话题)", "填消息链接"),
            ("va_td_web_req", "GetThreadId", "付费群助手 · 取 thread id", "填消息链接"),
            ("va_td_web_req", "GetMessageId", "付费群助手 · 取 msg id", "填消息链接"),
            ("va_td_web_req", "GetMessageUser", "付费群助手 · 取发送者", "填消息链接"),
            ("va_td_web_req", "GetMsgLocalDir", "付费群助手 · 取消息本地目录", "填消息链接"),
        ],
    },
    {
        "title": "任务进度",
        "desc": "清掉某个配置行残留的进度记录（桌面版「清理任务进度」）。",
        "items": [
            ("ecr_td_web_req", "GetTaskStats", "爬虫PRO · 任务统计", "填配置行 id"),
            ("ecr_td_web_req", "ClearTaskProgress", "爬虫PRO · 清理任务进度", "填配置行 id"),
            ("ecr_td_web_req", "BatchClearTaskProgress", "爬虫PRO · 批量清理进度", "id 用逗号分隔"),
            ("ecc_td_web_req", "GetTaskStats", "克隆PRO · 任务统计", "填配置行 id"),
            ("ecc_td_web_req", "GetTaskSyncProgress", "克隆PRO · 同步进度", "填配置行 id"),
            ("ecc_td_web_req", "ClearTaskProgress", "克隆PRO · 清理任务进度", "填配置行 id"),
            ("ecc_td_web_req", "BatchClearTaskProgress", "克隆PRO · 批量清理进度", "id 用逗号分隔"),
        ],
    },
    {
        "title": "媒体加工（付费群助手）",
        "desc": "目录整理、MD5 导出这些运维动作。",
        "items": [
            ("va_td_web_req", "GetSrcSubDirs", "列出源子目录", ""),
            ("va_td_web_req", "ReBuildSrcDirs", "重建源目录索引", ""),
            ("va_td_web_req", "MoveSrcDirs", "移动源目录", ""),
            ("va_td_web_req", "ExportMd5", "导出 MD5 清单", ""),
            ("va_td_web_req", "DelChatMd5", "清理会话 MD5 记录", "填会话 id"),
            ("va_td_web_req", "FreeDownloadUrl", "自由下载（按消息链接）", ""),
            ("va_td_web_req", "ImportFiles", "导入文件", "填目录简称"),
        ],
    },
    {
        "title": "清空历史记录",
        "desc": "桌面版各服务「清空历史」按钮。ids 留空表示全部。",
        "items": [
            ("ecr_td_web_req", "ClearCrawHis", "爬虫PRO · 清空爬取历史", "cid 列表，留空=全部"),
            ("ecr_td_web_req", "ClearSendHis", "爬虫PRO · 清空发送历史", "同上"),
            ("ecc_td_web_req", "ClearCrawHis", "克隆PRO · 清空爬取历史", "同上"),
            ("replace_td_web_req", "ClearCrawHis", "批量替换 · 清空爬取历史", "同上"),
            ("replace_td_web_req", "ClearReplaceHis", "批量替换 · 清空替换历史", "同上"),
            ("va_td_web_req", "ClearCrawHis", "付费群助手 · 清空爬取历史", "同上"),
        ],
    },
]


def _fields_of(channel: str, action: str) -> List[Dict[str, Any]]:
    sp = payloads.spec_of(channel, action)
    kind = sp.get("kind")
    if kind == "unit":
        return []
    typed = sp.get("typed") or {}
    names = list(sp.get("fields") or [])
    if not names:
        names = [sp.get("field", "value")]
    out = []
    for name in names:
        out.append({
            "name": name,
            "type": typed.get(name, {"int": "number", "bool": "checkbox",
                                     "list": "text", "json": "textarea",
                                     "str": "text"}.get(kind, "text")),
        })
    return out


def catalog() -> List[Dict[str, Any]]:
    out = []
    for g in _GROUPS:
        items = []
        for channel, action, title, desc in g["items"]:
            spec = payloads.spec_of(channel, action)
            items.append({
                "channel": channel,
                "action": action,
                "title": title,
                "desc": desc,
                "kind": spec.get("kind"),
                "hint": spec.get("hint", ""),
                "fields": _fields_of(channel, action),
            })
        out.append({"title": g["title"], "desc": g["desc"], "items": items})
    return out
