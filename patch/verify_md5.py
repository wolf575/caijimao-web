import struct
p=r"C:\Program1\caijimao430\caijimao430\app\crawler2.exe"
d=open(p,"rb").read()
TV,TO=0x140001000,0x400
def o(va): return TO+(va-TV)
for va in (0x1403bfbc0,0x14099d660,0x14141a1c0):
    print("pred 0x%x : %s"%(va,d[o(va):o(va)+3].hex()))
for va in (0x1402dc249,0x1402e3aec,0x1403205b9,0x140270889,0x1402c82fb,0x1406d6e39):
    print("site 0x%x : %s"%(va,d[o(va):o(va)+6].hex()))
