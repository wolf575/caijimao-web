# 架构

## 一句话

> 桌面版 = Rust 后端（`crawler2.exe`）+ PySide6 客户端。
> Web 版 = **同一个** Rust 后端（Wine 里跑）+ FastAPI 客户端。

功能等价不是靠"照着界面重新实现"，而是靠**保留原后端、只换客户端**——所有业务逻辑（任务调度、媒体流水线、上传、限速、TDLib 会话）都没动过。

```
┌─────────────────────────── 容器 ───────────────────────────┐
│                                                            │
│   浏览器 ──HTTP/SSE──►  FastAPI  (0.0.0.0:8080)            │
│                          │                                 │
│                          │ HTTP 127.0.0.1:3334  (控制面)    │
│                          │ WS   127.0.0.1:3333/ws (事件面)  │
│                          ▼                                 │
│                    Wine ──► crawler2.exe (Rust)            │
│                              ├── tdjson.dll  → Telegram    │
│                              ├── ffmpeg.exe  → 媒体加工     │
│                              └── sled / sqlite → /data      │
└────────────────────────────────────────────────────────────┘
```

为什么不需要 Xvfb：`crawler2.exe` 是**控制台程序**（Rust + axum + tokio），不起窗口。桌面版的窗口是另一个进程（PySide6 打的 PyInstaller 包）。我们把它彻底去掉，所以容器里没有图形栈。

## 三个组成部分

### 0. 程序目录与数据目录为什么分开

| 路径 | 内容 | 在哪 |
| --- | --- | --- |
| `/app` | `crawler2.exe`、依赖 DLL、`ffmpeg.exe` | 镜像层（不挂卷） |
| `/data/app` | `config.yml`、`ver`、`logs/`、`sled/`、`data/` | 卷（持久化） |

看起来把整个 `app/` 塞进卷更简单，但**在 Windows 上的 Docker Desktop 会失败**：
卷被映射成 virtiofs，Wine 无法从那里 mmap 并启动 57 MB 的 PE —— 直接返回 `rc=5`，
连一行输出都没有，日志里什么都看不到。

所以采用「程序在镜像、数据在卷」：`wine /app/crawler2.exe`（绝对路径），但把 cwd
设成 `/data/app`。后端所有相对路径（`config.yml`、`logs/`、`sled/`、`data/`）都落在卷里，
于是登录态和缓存能持久化；而可执行文件与 DLL 始终从镜像层加载，稳定可靠。
`/data/app/lib` 做成指向 `/app/lib` 的软链，兼容后端按 `cwd/lib` 找 DLL 的老习惯。

### 1. 后端（原样，未改动逻辑）

`payload/app/crawler2.exe`：Rust + axum 0.6 + tokio + sled + mongodb 驱动 + TDLib 1.8.59（`tdjson.dll`）。

- 控制面：`POST http://127.0.0.1:3334/req`，body 是 `{ "<channel>": { "<Action>": <value> } }`，回 `ok` 或 JSON。
- 事件面：`ws://127.0.0.1:3333/ws`，每帧是**「JSON 字符串组成的 JSON 数组」**（外层 `json.loads` 得到 list，每个元素再 `json.loads` 一次才是一个事件）。
- 日志：`app/logs/sys.log.YYYY-MM-DD-HH.log`（**按 UTC 小时滚动**）、`err.YYYY-MM-DD.log`（按天）。

只有三个字节被改（VIP 判定），见 README 的「关于收费限制」。

### 2. Web 控制台（`webui/`，本仓库原创）

| 文件 | 职责 |
| --- | --- |
| `parity.py` | **单一事实来源**：6 个通道、138 个动作、页面归属、每个动作的 value 覆盖。任何新动作先加这里。 |
| `backend.py` | 到后端的 HTTP 客户端。关键点：`trust_env=False`（否则 httpx 会读环境里的 `NO_PROXY` 并炸）、快照 `err.log` 偏移以捕获"HTTP 回 ok 但其实反序列化失败"的情况。 |
| `wsbridge.py` | WS 订阅 + 重连（1→30 s 退避）+ 事件环形缓冲 + 订阅者队列；把 VIP 状态持久化到 `/data/is_vip.json`。 |
| `auth.py` | bcrypt 密码、itsdangerous 会话 cookie、CSRF、按 IP 限速。随机密码只在首次启动打印一次。 |
| `app.py` | 路由 + 生命周期。页面走 303 跳转，`/api/*` 走 401 JSON。 |
| `templates/` | 9 个 Jinja 模板。`service.html` 是 5 个服务共用的通用页。 |
| `static/` | 深色主题 CSS + 无依赖 JS（`window.CJ`）。 |

### 3. 容器编排（`docker/`）

`entrypoint.sh` 是个极简 supervisor：

1. 首次启动初始化 `WINEPREFIX`（`wineboot --init`，镜像构建时已经做过一次）。
2. `wine crawler2.exe`（cwd 必须是 `/app`，因为后端按**当前工作目录**找 `config.yml`/`lib`/`logs`）。
3. `uvicorn webui.app:app`。
4. 后端崩了自动重启；Web 进程崩了则整个容器退出（交给 `restart: unless-stopped`）。
5. `trap TERM INT` → 先停 Web，再 `wineserver -k`。

`tini` 作为 PID 1 负责信号与僵尸回收。

## 数据流示例：点「启动服务」

```
浏览器  POST /api/action  channel=ecr_td_web_req action=StartService value=1  (+csrf)
   │
   ├─ auth.require()   → 无 cookie 则 401 JSON
   ├─ auth.check_csrf()→ token 不匹配则 400
   ├─ parity 白名单校验 → 未声明的动作直接 400（永不透传到后端）
   │
   ▼
BackendClient.call("ecr_td_web_req", "StartService", 1)
   │  POST http://127.0.0.1:3334/req  {"ecr_td_web_req":{"StartService":1}}
   │  同时记下 err.log 的当前偏移
   ▼
后端 axum 路由 → ecr-td::http_bus → 异步任务 → TDLib
   │
   ├─ 控制面回 200 "ok"
   ├─ 若反序列化失败：往 err.log 追加一行（HTTP 仍然是 ok！）
   └─ 状态变化：往 WS 推事件
   │
   ▼
BackendClient 读 err.log 新增字节 → 作为 `errors` 字段返回
   │
   ▼
浏览器  toast("ok") 或 toast(红, errors)
        WS 事件同时经 /api/stream (SSE) 推到所有打开的页面
```

**为什么要抓 `err.log`**：后端对未知动作也回 `ok`，只有 `err.log` 会写 `unknown variant`。不抓就等于瞎了——`scripts/verify_parity.py` 正是靠这一点做全量枚举核对的。

## 一致性（parity）是怎么保证的

1. `parity.py` 声明 6 通道 138 动作。
2. `scripts/verify_parity.py` 对每个通道发一个假动作，从 `err.log` 里正则出后端真实的 `expected one of ...` 列表，与声明做集合比对。
3. `/api/parity` 在运行时再核一次"是否有动作没有任何入口"：每个动作必须属于某个页面，或属于 `/admin/console`。
4. `/admin/console` 可以手发**任意**通道 + 任意动作 + 任意 payload，是永不失效的兜底。

三件事同时成立，才敢说"功能一一对应"。

## ffmpeg 兜底

后端会执行 `ffmpeg.exe`（媒体加工：转码、压缩、加自定义水印）。它在容器里由 Wine 拉起。

如果 Wine 跑不了它（少数发行版会因为缺少某些 DLL 而失败），按顺序试：

1. **换 Wine 版本**：`debian:bookworm` 自带 Wine 8；换成 `scottyhardy/docker-wine` 或 `winehq-stable` 通常就好了。
2. **Linux ffmpeg + PE 壳**：把容器里的 Linux `ffmpeg` 复制成 `ffmpeg.exe`，前面加一个 20 行的 PE 转发器（其实 Wine 对无扩展名的 ELF 也能执行，直接用符号链接试一次最快）。
3. **拆开部署**：后端放在 Windows 主机/另一台机器上，容器只跑 Web 控制台，用 `CJ_BACKEND_HTTP` / `CJ_BACKEND_WS` 指过去。这条路一定可行，只是失去了"单容器"的便利。

`/healthz` 会在后端 ping 不通时返回 503，方便你判断卡在哪一层。

## 为什么不做原生 Linux 重写

`crawler2.exe` 是 57 MB 的 Rust 二进制，内含 TDLib 编排、任务状态机、SQLite/sled 持久化、媒体流水线、上传限速、多实例代理。重写成 Linux 原生版本的工作量是"重写整个产品"，而且没有可验证的等价标准。

现在的做法给了一个**可验证的等价标准**：`/api/parity` 的 138 动作 + 桌面版界面作为对照。将来真要做原生版，这份 API 契约就是验收规范，Wine 镜像就是 oracle。

## 端口与进程清单

| 端口 | 谁 | 是否对外 |
| --- | --- | --- |
| 8080 | FastAPI | 是（唯一入口） |
| 3334 | 后端 HTTP 控制面 | 否（容器内 127.0.0.1） |
| 3333 | 后端 WS 事件面 | 否（容器内 127.0.0.1） |

进程：`tini`(1) → `entrypoint.sh` → `wine crawler2.exe` + `uvicorn`。
