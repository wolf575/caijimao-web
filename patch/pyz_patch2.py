import marshal, os, zlib, struct, io
BASE = r"C:\Users\ligang\Desktop\文档\vibe coding\purge\work\caijimao430"
PYZ  = os.path.join(BASE,"extract","PYZ-00.pyz")
OUT  = os.path.join(BASE,"PYZ-00.patched.pyz")

NEW_HTML = """
<!DOCTYPE html>
<html>
<style>
table, th, td {
  border: 2px solid blue;
  border-collapse: collapse;
  padding: 10px;
}
</style>
<head>
<meta charset="utf-8">
</head>
<body>

<h1 style="text-align: center;"><strong>服务状态</strong></h1>
<hr style="padding-left: 80px;" />

<h2 style="padding-left: 80px;">您当前的 「客户ID」为：</h2>
<h1 style="padding-left: 80px;"><span style="color: #3598db;">/hd_id/</span></h1>
<h3 style="padding-left: 80px;">当前「客户ID」的各服务状态：</h3>

<table>
  <thead>
    <tr>
      <th>插件id</th>
      <th>插件名称</th>
      <th>注册时间</th>
      <th>过期时间</th>
      <th>状态</th>
    </tr>
  </thead>
  <tbody>
    /lease_all/
  </tbody>
</table>

<p style="padding-left: 80px;">&nbsp;</p>
/hd_list_str/
<hr style="padding-left: 80px;" />
<h3 style="padding-left: 80px;"><strong>官方频道：</strong><span style="color: #3598db;"><strong>@aicaiji</strong></span></h3>
<h3 style="padding-left: 80px;"><strong>客服：</strong><span style="color: #3598db;">@tgcaijimao</span></h3>

</body>
</html>
"""

EXACT = {
  "widgets.navtree": {
    "\u6309\u94ae\u673a\u5668\u4eba\u670d\u52a1(VIP)": "\u6309\u94ae\u673a\u5668\u4eba\u670d\u52a1",
    "\u9891\u9053\u7fa4\u514b\u9686PRO(VIP)": "\u9891\u9053\u7fa4\u514b\u9686PRO",
    "\u6279\u91cf\u66ff\u6362/\u5220\u9664\u670d\u52a1(VIP)": "\u6279\u91cf\u66ff\u6362/\u5220\u9664\u670d\u52a1",
    "\u4ed8\u8d39\u7fa4\u52a9\u624b(VIP)": "\u4ed8\u8d39\u7fa4\u52a9\u624b",
    "\u722c\u866bPRO(VIP)": "\u722c\u866bPRO",
  },
  "worder": {
    "vip": "\u5df2\u5f00\u901a",
    "\u672a\u5f00\u901a\u6216\u5df2\u8fc7\u671f": "\u5df2\u5f00\u901a",
    " \u5373\u5c06\u8fc7\u671f": "\u5df2\u5f00\u901a",
    "\u8d85\u7ea7vip": "\u8d85\u7ea7\u4f1a\u5458",
    "\u540e\u53f0\u672a\u8fde\u63a5\uff0c\u65e0\u6cd5\u83b7\u53d6\u5230\u6388\u6743\u4fe1\u606f": "\u540e\u53f0\u672a\u8fde\u63a5\uff0c\u8bf7\u7a0d\u540e\u518d\u8bd5",
  },
  "pub_utils.w_cc_msg_type": {
    "\n\u82e5\u60a8\u662fVIP\u7528\u6237\uff0c\u8f6f\u4ef6\u521a\u542f\u52a8\u65f6\u7531\u4e8e\u7f51\u7edc\u901a\u8baf\u539f\u56e0\uff0c\u9700\u8981\u70b9\u51fb\u4e0a\u65b9\u3010\u5237\u65b0\u3011\u6309\u94ae\u65b9\u53ef\u52a0\u8f7dVIP\u8eab\u4efd\n\uff08\u53ef\u591a\u5237\u65b0\u51e0\u6b21\uff0c\u80cc\u666f\u7531\u7070\u8272\u53d8\u4e3a\u7eaf\u8272\u5373\u8868\u793a\u8eab\u4efd\u52a0\u8f7d\u6210\u529f\uff09\n": "\n\u8f6f\u4ef6\u521a\u542f\u52a8\u65f6\uff0c\u82e5\u914d\u7f6e\u672a\u663e\u793a\uff0c\u53ef\u70b9\u51fb\u4e0a\u65b9\u3010\u5237\u65b0\u3011\u6309\u94ae\u91cd\u65b0\u52a0\u8f7d\u3002\n",
  },
  "btnbots.w_bb_list_button": {
    "\n\u6b64\u5904\u662f\u6dfb\u52a0\u60a8\u60f3\u8981\u7684\u673a\u5668\u4eba\u6309\u94ae\uff0c\u663e\u793a\u5728\u673a\u5668\u4eba\u53d1\u9001\u7684\u6d88\u606f\u5e95\u90e8\uff01\n\u672c\u529f\u80fd\u514d\u8d39\u7248\u672c\u4e5f\u53ef\u4f7f\u7528\uff01        \n        ": "\n\u6b64\u5904\u662f\u6dfb\u52a0\u60a8\u60f3\u8981\u7684\u673a\u5668\u4eba\u6309\u94ae\uff0c\u663e\u793a\u5728\u673a\u5668\u4eba\u53d1\u9001\u7684\u6d88\u606f\u5e95\u90e8\uff01\n        ",
  },
}

# substring cleanups applied to any module listed
SUBSTR = {
  "ecc.dlgs.discuss_sub": [("\u9700\u8981\u8d2d\u4e70\u3010\u5a92\u4f53\u52a0\u5de5\u3011\u7684\u670d\u52a1", "\u9700\u8981\u5f00\u542f\u3010\u5a92\u4f53\u52a0\u5de5\u3011\u529f\u80fd")],
  "ecc.dlgs.single_sub":  [("\u9700\u8981\u8d2d\u4e70\u3010\u5a92\u4f53\u52a0\u5de5\u3011\u7684\u670d\u52a1", "\u9700\u8981\u5f00\u542f\u3010\u5a92\u4f53\u52a0\u5de5\u3011\u529f\u80fd")],
  "ecc.dlgs.topic_sub":   [("\u9700\u8981\u8d2d\u4e70\u3010\u5a92\u4f53\u52a0\u5de5\u3011\u7684\u670d\u52a1", "\u9700\u8981\u5f00\u542f\u3010\u5a92\u4f53\u52a0\u5de5\u3011\u529f\u80fd")],
  "ecr.dlgs.craw_sub":    [("\u9700\u8981\u8d2d\u4e70\u3010\u5a92\u4f53\u52a0\u5de5\u3011\u7684\u670d\u52a1", "\u9700\u8981\u5f00\u542f\u3010\u5a92\u4f53\u52a0\u5de5\u3011\u529f\u80fd")],
}

TARGETS = set(EXACT) | set(SUBSTR)

def fix(code, module):
    consts = list(code.co_consts); n = 0
    for i, c in enumerate(consts):
        if isinstance(c, str):
            if module == "worder" and c.lstrip().startswith("<!DOCTYPE html>"):
                consts[i] = NEW_HTML; n += 1
            elif c in EXACT.get(module, {}):
                consts[i] = EXACT[module][c]; n += 1
            else:
                for a, b in SUBSTR.get(module, []):
                    if a in c:
                        consts[i] = c.replace(a, b); n += 1
        elif hasattr(c, "co_consts"):
            nc, k = fix(c, module)
            if k:
                consts[i] = nc; n += k
    if n: return code.replace(co_consts=tuple(consts)), n
    return code, 0

data = open(PYZ, "rb").read()
assert data[:4] == b"PYZ\x00"
pyc_magic = data[4:8]
toc = marshal.loads(data[struct.unpack_from("!I", data, 8)[0]:])
entries = []; report = {}
for name, (tc, pos, length) in toc:
    plain = zlib.decompress(data[pos:pos+length])
    if name in TARGETS:
        code, k = fix(marshal.loads(plain), name)
        plain = marshal.dumps(code)
        report[name] = k
    entries.append((name, tc, zlib.compress(plain, 6)))

buf = io.BytesIO()
buf.write(b"PYZ\x00"); buf.write(pyc_magic); buf.write(b"\x00\x00\x00\x00")
newtoc = []
for name, tc, payload in entries:
    p = buf.tell(); buf.write(payload); newtoc.append((name, (tc, p, len(payload))))
toc_pos = buf.tell()
buf.write(marshal.dumps(newtoc))
buf.seek(8); buf.write(struct.pack("!I", toc_pos))
out = buf.getvalue()
open(OUT, "wb").write(out)
print("written", OUT, len(out), "toc_pos", toc_pos)
print("patched modules:", report)