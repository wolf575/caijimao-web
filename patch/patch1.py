P = r"C:\Users\ligang\Desktop\文档\vibe coding\purge\work\caijimao430\crawler2.exe"
O = r"C:\Users\ligang\Desktop\文档\vibe coding\purge\work\caijimao430\crawler2.patched.exe"
data = bytearray(open(P,"rb").read())
BASE_VA, BASE_OFF = 0x140001000, 0x400
def va2off(va): return BASE_OFF + (va - BASE_VA)
cands = [0x1403bfbc0, 0x14099d660, 0x14141a1c0]
for va in cands:
    off = va2off(va)
    before = bytes(data[off:off+3])
    data[off:off+3] = b"\xB0\x01\xC3"
    print("patched VA 0x%x off 0x%x : %s -> b0 01 c3" % (va, off, before.hex(" ")))
open(O,"wb").write(data)
print("written", O, len(data))