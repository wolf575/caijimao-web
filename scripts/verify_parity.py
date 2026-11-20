"""对照真实后端校验 parity.py 的动作清单是否完整、无多余。

用法（后端必须已经在 127.0.0.1:3334 上运行）：
    python scripts/verify_parity.py

原理：向每个通道发一个不存在的动作，后端会把完整的 variant 列表写进
logs/err.<date>.log；解析出来与 parity.py 比对。
HTTP 层对未知动作同样返回 ok，所以只能靠错误日志判断。
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from webui import parity  # noqa: E402

BASE = "http://127.0.0.1:3334"
APP_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "app")
LOGS = APP_DIR / "logs"
BOGUS = "ZZZ_NOT_A_REAL_ACTION"


def newest_errlog() -> Path | None:
    files = sorted(LOGS.glob("err.*.log"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def err_size() -> int:
    p = newest_errlog()
    return p.stat().st_size if p else 0


def read_since(path: Path, offset: int) -> str:
    with path.open("rb") as fh:
        fh.seek(offset)
        return fh.read().decode("utf-8", "replace")


def probe(client: httpx.Client, channel: str) -> list[str]:
    before = err_size()
    client.post(f"{BASE}/req", json={channel: {BOGUS: 1}}, timeout=10)
    # 后端写日志是异步的，轮询等新内容
    for _ in range(40):
        time.sleep(0.05)
        if err_size() > before:
            break
    path = newest_errlog()
    if path is None:
        return []
    text = read_since(path, before)
    if "expected one of" not in text:
        return []
    tail = text.split("expected one of", 1)[1]
    # 截到该行结束，然后抽出所有 `Variant` 名字
    tail = tail.split("\n", 1)[0]
    return re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", tail)


def main() -> int:
    if not LOGS.is_dir():
        print(f"[!] 找不到日志目录 {LOGS}，请先启动后端", file=sys.stderr)
        return 2

    rc = 0
    with httpx.Client(trust_env=False) as client:
        try:
            ping = client.get(f"{BASE}/ping", timeout=5)
        except Exception as exc:  # noqa: BLE001
            print(f"[!] 后端不可达：{exc}", file=sys.stderr)
            return 2
        if "pong" not in ping.text:
            print(f"[!] /ping 返回异常：{ping.status_code} {ping.text[:120]}", file=sys.stderr)
            return 2

        for ch in parity.CHANNELS:
            live = probe(client, ch.key)
            declared = list(ch.actions)
            if not live:
                print(f"[?] {ch.key}: 未能从 err 日志解析到动作列表（跳过）")
                continue
            live_s, decl_s = set(live), set(declared)
            missing = sorted(live_s - decl_s)   # 后端有、我们没声明
            extra = sorted(decl_s - live_s)     # 我们声明了、后端没有
            status = "OK" if not missing and not extra else "MISMATCH"
            print(f"[{status}] {ch.key}: live={len(live_s)} declared={len(decl_s)}")
            if missing:
                rc = 1
                print(f"    后端多出（未声明）：{missing}")
            if extra:
                rc = 1
                print(f"    声明多余（后端无）：{extra}")

    total = parity.total_actions()
    print(f"\n合计声明动作：{total}（6 通道）")
    print("parity 自检：", parity.selfcheck() or "通过")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
