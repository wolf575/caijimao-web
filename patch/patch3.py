import hashlib, struct

SRC = r"C:\Users\ligang\Desktop\文档\vibe coding\purge\work\caijimao430\crawler2.v2.exe"
DST = r"C:\Users\ligang\Desktop\文档\vibe coding\purge\work\caijimao430\crawler2.v3.exe"

TV, TO = 0x140001000, 0x400
def va2off(va): return TO + (va - TV)

d = bytearray(open(SRC, "rb").read())

# va-vip-check gate in func 0x1401da9e0: test bl,1 / je 0x1401e2693
# bl = is_vip(0x1403bfbc0) which we forced to 1 -> falls into "vip已过期" stop.
# Force the je to always jump to the OK path.
SITES = [
    (0x1401e2609, 0x1401e2693),
]

for va, tgt in SITES:
    o = va2off(va)
    orig = bytes(d[o:o+6])
    assert orig[0] == 0x0F and orig[1] == 0x84, ("not a near je", hex(va), orig.hex())
    old_rel = struct.unpack_from("<i", d, o+2)[0]
    assert va + 6 + old_rel == tgt, ("target mismatch", hex(va), hex(va+6+old_rel), hex(tgt))
    rel = tgt - (va + 5)
    new = b"\xE9" + struct.pack("<i", rel) + b"\x90"
    d[o:o+6] = new
    print("patch 0x%x  %s -> %s   jmp 0x%x (rel %+d)" % (va, orig.hex(), new.hex(), tgt, rel))

open(DST, "wb").write(d)
print("size", len(d))
print("md5", hashlib.md5(bytes(d)).hexdigest())
