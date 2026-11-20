#!/usr/bin/env python3
"""探测每个后端动作能接受的 payload 形态。

背景：后端的 HTTP 层对任何请求都回 `ok`，真正的错误只写进
`logs/err.<date>.log` 的 `deserialize_err`。而且不同动作的 payload 类型完全不同
（`1` / `true` / `"str"` / `null` / 结构体 / 数组），用统一的 `1` 去发就会大量报
`invalid type: integer '1', expected a boolean|a string|unit|struct TdConfig`。

这个脚本对 6 个通道的每个动作依次试若干候选值，看 err 日志里有没有新增
deserialize_err，从而得出每个动作该发什么。

在容器内跑：
    docker cp scripts/probe_payloads.py caijimao-web:/tmp/
    docker exec caijimao-web /opt/venv/bin/python /tmp/probe_payloads.py

输出：JSON 到 /tmp/payloads.json，同时打印一份摘要。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request

BACKEND = os.environ.get("CJ_BACKEND_HTTP", "http://127.0.0.1:3334")
LOGS = os.environ.get("CJ_LOGS_DIR", "/data/app/logs")
OUT = os.environ.get("CJ_OUT", "/tmp/payloads.json")

sys.path.insert(0, "/srv")
try:
    from webui.parity import CHANNELS  # type: ignore
except Exception:  # 允许不依赖 webui 单独跑
    CHANNELS = []

# 候选 payload，按「最可能」到「最不可能」排序
CANDIDATES = [
    1,
    True,
    "1",
    None,
    {},
    [],
    {"id": 1},
    [1],
    [1, 1],
    "",
    0,
    False,
]

ERR_RE = re.compile(r"deserialize_err: (.*?) at line \d+ column \d+")


def newest_errlog() -> str | None:
    try:
        names = [n for n in os.listdir(LOGS) if n.startswith("err.") and n.endswith(".log")]
    except OSError:
        return None
    if not names:
        return None
    names.sort()
    return os.path.join(LOGS, names[-1])


def err_size(path: str | None) -> int:
    if not path:
        return 0
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def read_from(path: str, offset: int) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def post(channel: str, action: str, value) -> str:
    body = json.dumps({channel: {action: value}}, ensure_ascii=False).encode()
    req = urllib.request.Request(
        BACKEND + "/req", data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", "replace").strip()
    except Exception as exc:  # noqa: BLE001
        return f"<http-error {exc}>"


def probe(channel: str, action: str) -> dict:
    """返回 {ok_value, errors:[...]}；ok_value 为 None 表示所有候选都被拒。"""
    errlog = newest_errlog()
    tried = []
    for cand in CANDIDATES:
        off = err_size(errlog)
        resp = post(channel, action, cand)
        time.sleep(0.12)
        chunk = read_from(errlog, off) if errlog else ""
        m = ERR_RE.search(chunk)
        if m:
            tried.append({"value": cand, "error": m.group(1).strip()})
            continue
        return {"value": cand, "response": resp[:120], "rejected": tried}
    return {"value": None, "rejected": tried}


def main() -> int:
    result: dict[str, dict] = {}
    for ch in CHANNELS:
        key = ch.key
        result[key] = {}
        for act in ch.actions:
            r = probe(key, act)
            result[key][act] = r
            flag = "OK " if r["value"] is not None else "?? "
            shown = json.dumps(r["value"], ensure_ascii=False)
            last = (r.get("rejected") or [{}])[-1].get("error", "")
            print(f"{flag}{key}.{act} -> {shown}   {last[:70]}")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    unknown = sum(1 for c in result.values() for a in c.values() if a["value"] is None)
    print(f"\n共 {sum(len(c) for c in result.values())} 个动作，未探明 {unknown} 个 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
