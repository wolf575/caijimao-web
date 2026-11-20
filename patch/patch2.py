import hashlib, struct

SRC = r"C:\Users\ligang\Desktop\文档\vibe coding\purge\work\caijimao430\crawler2.v1.exe"
DST = r"C:\Users\ligang\Desktop\文档\vibe coding\purge\work\caijimao430\crawler2.v2.exe"

TV, TO = 0x140001000, 0x400
def va2off(va): return TO + (va - TV)

d = bytearray(open(SRC, "rb").read())

# (je_site, ok_target) -- both are VAs; the je is a 6-byte 0F 84 rel32
SITES = [
    (0x1402dc249, 0x1402dc389),
    (0x1402e3aec, 0x1402e35b2),
    (0x1403205b9, 0x1403206df),
    (0x140270889, 0x1402709c9),
    (0x1402c82fb, 0x1402c841c),
    (0x1406d6e39, 0x1406d6a6d),
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
