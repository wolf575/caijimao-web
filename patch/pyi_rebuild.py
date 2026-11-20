import struct, os
BASE = r"C:\Users\ligang\Desktop\文档\vibe coding\purge\work\caijimao430"
SRC  = os.path.join(BASE,"caijimao.orig.exe")
NEWPYZ = os.path.join(BASE,"PYZ-00.patched.pyz")
OUT  = os.path.join(BASE,"caijimao.patched.exe")
MAGIC = b"MEI\014\013\012\013\016"
def pad_for(nb): return 16 - ((18+len(nb)) % 16)

data = open(SRC,"rb").read()
idx = data.rfind(MAGIC)
pkg_len, toc_off, toc_len, pyver = struct.unpack_from("!IIII", data, idx+8)
pylib = data[idx+24:idx+88].rstrip(b"\x00").decode()
arch_start = (idx+88) - pkg_len
print("arch_start",hex(arch_start),"entries toc_len",toc_len)

p = arch_start + toc_off
end = p + toc_len
entries=[]
while p < end:
    elen, off, clen, ulen, cflag, tc = struct.unpack_from("!IIIIBc", data, p)
    name = data[p+18:p+elen].rstrip(b"\x00").decode("utf-8","replace")
    entries.append(dict(name=name, off=off, clen=clen, ulen=ulen, cflag=cflag, tc=tc, elen=elen))
    p += elen
print("entries", len(entries), "last", entries[-1]["name"])
assert entries[-1]["name"] == "PYZ-00.pyz" and entries[-1]["cflag"] == 0
assert toc_off == sum(e["clen"] for e in entries)
acc=0
for e in entries:
    assert e["off"] == acc, (e["name"], e["off"], acc)
    acc += e["clen"]
    assert e["elen"] == 18+len(e["name"].encode())+pad_for(e["name"].encode()), e["name"]
assert pkg_len == toc_off + toc_len + 88
print("original invariants OK")

newpyz = open(NEWPYZ,"rb").read()
out = bytearray(data[:arch_start])
tocblob = bytearray()
for e in entries:
    payload = data[arch_start+e["off"]: arch_start+e["off"]+e["clen"]]
    if e["name"] == "PYZ-00.pyz":
        payload = newpyz
        e["ulen"] = len(newpyz)
    e["off"] = len(out) - arch_start
    e["clen"] = len(payload)
    out += payload
    nb = e["name"].encode()
    pad = pad_for(nb)
    tocblob += struct.pack("!IIIIBc", 18+len(nb)+pad, e["off"], e["clen"], e["ulen"], e["cflag"], e["tc"]) + nb + b"\x00"*pad

new_toc_off = len(out) - arch_start
new_toc_len = len(tocblob)
out += tocblob
new_pkg_len = new_toc_off + new_toc_len + 88
out += MAGIC + struct.pack("!IIII", new_pkg_len, new_toc_off, new_toc_len, pyver) + pylib.encode().ljust(64, b"\x00")
open(OUT,"wb").write(bytes(out))
print("written", OUT, len(out), "toc_off", new_toc_off, "toc_len", new_toc_len, "pkg_len", new_pkg_len)

# self-check: reparse and compare payloads
d2 = open(OUT,"rb").read()
i2 = d2.rfind(MAGIC)
pl2, to2, tl2, pv2 = struct.unpack_from("!IIII", d2, i2+8)
as2 = (i2+88) - pl2
assert as2 == arch_start and pv2 == pyver and pl2 == to2+tl2+88
p2 = as2+to2; e2 = p2+tl2; n2=0; diff=[]
while p2 < e2:
    elen, off, clen, ulen, cflag, tc = struct.unpack_from("!IIIIBc", d2, p2)
    name = d2[p2+18:p2+elen].rstrip(b"\x00").decode("utf-8","replace")
    orig = next(x for x in entries if x["name"]==name)
    a = data[arch_start+orig["off"]:arch_start+orig["off"]+orig["clen"]]
    b = d2[as2+off:as2+off+clen]
    if a != b: diff.append(name)
    n2+=1
    p2+=elen
print("selfcheck entries", n2, "payload diffs", diff)