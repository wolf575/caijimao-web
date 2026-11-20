#!/usr/bin/env python3
"""解除采集猫 4.3.0 后端的收费限制（三个字节，三个函数）。

原理
----
后端里所有「未开通该服务的 vip 功能」的分支，最终都读同一个判定函数的返回值：

    AL = 0  -> 已开通（走正常业务）
    AL = 1  -> 未开通（打日志并 return）
    AL = 2  -> Pending（异步，稍后重试）

这个函数有三个单态化副本，而且**调用点的语义并不一致**：前两个副本返回 0 才
表示已开通，第三个副本的调用点是相反的（返回 1 才表示已开通）。所以三个都得按
各自的极性改，写成一个常量反而会把某些功能锁死。

把每个副本的开头改成 `mov al, <imm8>; ret`（`B0 xx C3`），函数就直接返回常量，
后面几百条指令变成死代码。这样不需要动任何分支，也不会破坏栈（函数入口还没
push 任何寄存器）。

    VA 0x1403bfbc0  文件 0x3befc0  ->  B0 00 C3   (返回 0 = 已开通)
    VA 0x14099d660  文件 0x99ca60  ->  B0 00 C3   (返回 0 = 已开通)
    VA 0x14141a1c0  文件 0x14195c0 ->  B0 01 C3   (返回 1 = 已开通，极性相反)

VA -> 文件偏移：off = 0x400 + (va - 0x140001000)     # .text 段，ImageBase 0x140000000

用法
----
    python patch4.py crawler2.exe crawler2.patched.exe
    python patch4.py crawler2.exe --check          # 只看当前状态，不写文件
    python patch4.py crawler2.exe out.exe --revert # 还原成原始字节

输入必须是 UPX 解压后的 crawler2.exe（约 56,971,264 字节）。
原版是 UPX 4.10 压缩的，先 `upx -d crawler2.exe`。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

IMAGE_BASE = 0x140000000
TEXT_VA = 0x140001000
TEXT_OFF = 0x400

#: (VA, 补丁后的 imm8, 说明)
SITES: tuple[tuple[int, int, str], ...] = (
    (0x1403BFBC0, 0x00, "VIP 判定副本 #1 —— 返回 0 表示已开通"),
    (0x14099D660, 0x00, "VIP 判定副本 #2 —— 返回 0 表示已开通"),
    (0x14141A1C0, 0x01, "VIP 判定副本 #3 —— 该调用点极性相反，返回 1 表示已开通"),
)

#: 三个函数入口原本都是 `push rbp; push r15; push r14`（55 41 56）
ORIGINAL_PREFIX = b"\x55\x41\x56"

PATCH = lambda imm: bytes((0xB0, imm, 0xC3))  # mov al, imm8 ; ret


def va_to_off(va: int) -> int:
    return TEXT_OFF + (va - TEXT_VA)


def md5(data: bytes | bytearray) -> str:
    return hashlib.md5(data).hexdigest()


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}

    if not args:
        print(__doc__)
        return 2

    src = Path(args[0])
    if not src.is_file():
        print(f"找不到输入文件：{src}", file=sys.stderr)
        return 1

    data = bytearray(src.read_bytes())
    print(f"输入   {src}  ({len(data):,} 字节, md5 {md5(data)})")

    check_only = "--check" in flags
    revert = "--revert" in flags
    dst = Path(args[1]) if len(args) > 1 and not check_only else None

    ok = True
    for va, imm, desc in SITES:
        off = va_to_off(va)
        cur = bytes(data[off : off + 3])
        if revert:
            want = ORIGINAL_PREFIX
        else:
            want = PATCH(imm)

        if revert:
            if cur == ORIGINAL_PREFIX:
                print(f"  {desc}\n    VA 0x{va:012x} off 0x{off:08x} 已是原始字节 {cur.hex()}")
                continue
            if cur != PATCH(imm):
                print(f"  [跳过] VA 0x{va:012x} off 0x{off:08x} 字节意外：{cur.hex()}")
                ok = False
                continue
            data[off : off + 3] = ORIGINAL_PREFIX
            print(f"  {desc}\n    VA 0x{va:012x} off 0x{off:08x} 还原 {cur.hex()} -> {ORIGINAL_PREFIX.hex()}")
            continue

        if cur == want:
            print(f"  {desc}\n    VA 0x{va:012x} off 0x{off:08x} 已打过 {cur.hex()}")
            continue
        if cur != ORIGINAL_PREFIX:
            print(
                f"  [失败] VA 0x{va:012x} off 0x{off:08x} 期望原始字节 "
                f"{ORIGINAL_PREFIX.hex()}，实际 {cur.hex()}（不是这个版本？）",
                file=sys.stderr,
            )
            ok = False
            continue
        data[off : off + 3] = want
        verb = "将补丁" if check_only else "补丁"
        print(f"  {desc}\n    VA 0x{va:012x} off 0x{off:08x} {verb} {cur.hex()} -> {want.hex()}")

    if check_only or dst is None:
        print("（--check：未写入文件）")
        return 0 if ok else 1

    if not ok:
        print("有失败项，未写出文件。", file=sys.stderr)
        return 1

    dst.write_bytes(data)
    print(f"输出   {dst}  ({len(data):,} 字节, md5 {md5(data)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
