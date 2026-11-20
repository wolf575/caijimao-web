# API 契约

本文件是 Web 版与后端之间的完整契约，也是「功能一一对应」的验收规范。
机器可读版本在 [`webui/parity.py`](../webui/parity.py)，运行时自检接口是 `GET /api/parity`。

## 0. 两层接口

### 0.1 Web → 浏览器（本仓库）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/login` | 登录页 |
| POST | `/login` | `username` / `password` / `next`；成功 303 + `cj_session` cookie |
| POST | `/logout` | 清 cookie |
| GET | `/` `/td-login` `/ecr` `/ecc` `/replace` `/va` `/btn-bot` `/settings` `/logs` `/admin/console` | HTML 页面（需登录） |
| POST | `/api/action` | `channel` `action` `value` `csrf_token` → `{ok,status,channel,action,data,errors}` |
| GET | `/api/state` | `{ok,backend,ws,is_vip,buses,log_tail}` |
| GET | `/api/stream` | SSE：`event: hello`（快照）+ `event: event`（逐条 WS 事件） |
| GET | `/api/logs?kind=sys\|err&lines=N` | 日志尾部 |
| GET | `/api/parity` | `{ok,channels,actions,problems,console_only}` |
| GET | `/healthz` | `{ok,backend,ws}`；后端不可用时 503 |

`/api/*` 未登录 → **401 JSON**；页面未登录 → **303 → /login?next=…**。

### 0.2 Web → 后端（原版 crawler2.exe，只读契约）

```
POST http://127.0.0.1:3334/req
Content-Type: application/json

{ "<channel>": { "<Action>": <value> } }
```

- `value` 的形态由动作决定：`1`、字符串、整数数组、对象。
- 成功回 `ok` 或 JSON 文本；**未知动作也回 `ok`**，真正的错误只写进 `err.YYYY-MM-DD.log`。
- `GET http://127.0.0.1:3334/ping` → `pong`（唯一的 HTTP GET）。

事件面：

```
ws://127.0.0.1:3333/ws
帧格式：["{\"bus\":{\"Event\":payload}}", "…"]      ← JSON 数组，元素是 JSON 字符串
```

## 1. 通道与动作总表（6 通道 / 138 动作）

`value` 列写 `1` 表示该动作只需要一个占位值；`[id]` 表示传 id 数组；`{…}` 表示传 JSON 对象。

### 1.1 `td_web_req` — TD 全局 / 登录（38）

事件总线 `td_login_ws_bus`，默认页 `/settings`。

| action | 页面 | 说明 |
| --- | --- | --- |
| `GetHD` | `/` | 取客户 ID + 客户列表 |
| `GetVersion` | `/` | 取版本号 |
| `GetLease` | `/` | 取租约（`signature` / `list` / `local_expired`） |
| `GetMyChatsFull` | `/td-login` | 会话全量列表 |
| `NotifyMyChats` | `/td-login` | 让后端重新推送会话列表 |
| `DoLogin` / `DoLogout` | `/td-login` | 登录 / 退出 |
| `SendPhone` | `/td-login` | value = 手机号字符串 |
| `SendAuthCode` | `/td-login` | value = 验证码字符串 |
| `SendPassword` | `/td-login` | value = 二次验证密码字符串 |
| `BatchExitChat` / `JoinChat` / `JoinChatOfMsgLink` / `ToMyChatsOtherOfMsgLink` | `/td-login` | 会话管理 |
| `MsgUrl` / `DispatchUrlMarkDown` | `/ecr` | 消息链接解析 |
| `GetAntConfig` / `FlushAntConfig` | `/settings` | api_id / api_hash / req_limit / phone / hide_phone / proxy |
| `FlushUiProxies` | `/settings` | value = 代理数组 `[{enabled,server,port,user_name,password,secret,tp}]` |
| `ReloadCfg` | `/settings` | 重读配置 |
| `GetFileNameReplaces` / `FlushFileNameReplaces` | `/settings` | 文件名替换表 |
| `GetHostCfg` / `FlushHostCfg` | `/settings` | 主机连接配置 |
| `GetEncoder` / `FlushEncoder` | `/settings` | 编码器 |
| `GetFFMpegThreadCount` / `FlushFFMpegThreadCount` | `/settings` | ffmpeg 线程数 |
| `GetFFMpegSpeedDecode` / `FlushFFMpegSpeedDecode` | `/settings` | 解码加速开关 |
| `GetSqliteSyncOff` / `FlushSqliteSyncOff` | `/settings` | sqlite 同步模式 |
| `SetHdPwd` / `UpgradeHd` | `/settings` | value = `{old_hd, raw_pwd}` |
| `TestFootPrint` / `StopTestFootPrint` | `/settings` | 指纹测试 |
| `StopProg` | `/settings` | 让后端进程退出 |
| `None` | **仅 `/admin/console`** | 占位枚举，无实际行为 |

### 1.2 `ecr_td_web_req` — 爬虫PRO（25）

事件总线 `ecr_td_ws_bus`，页面 `/ecr`。

`Ping` `StartService` `StopService` `StopServiceOnlyCraw` `GetTaskStats` `GetCfg` `FlushCfg` `GetCfgRow` `FlushCfgRow` `RmCfgRows` `StartCfgRows` `StopCfgRows` `ClearTaskProgress` `BatchClearTaskProgress` `SetCrawTo` `ClearSendHis` `GetThreadId` `GetMessageId` `GetMessageUser` `GetBackupFiles` `RestoreCfg` `RegexReplace` `TestReplaceBatch` `TestMarkdown` `SendMessage`

### 1.3 `ecc_td_web_req` — 频道群克隆PRO（28）

事件总线 `ecc_td_ws_bus`，页面 `/ecc`。

在 ecr 的基础上多出 `SetMultiMainCrawTo` `SetCrawToBatch` `SmartGetThreadId` `GetMessageSender` `GetTaskSyncProgress`，少 `ClearSendHis` `StopServiceOnlyCraw`。

### 1.4 `replace_td_web_req` — 批量替换/删除服务（9）

事件总线 `replace_td_ws_bus`，页面 `/replace`。

`Ping` `StartService` `StopService` `GetCfg` `FlushCfg` `GetBackupFiles` `RestoreCfg` `ClearCrawHis` `ClearReplaceHis`

### 1.5 `va_td_web_req` — 付费群助手（31）

事件总线 `va_td_ws_bus`，页面 `/va`。

`Ping` `StartService` `StopService` `GetTaskStats` `GetCfg` `FlushCfg` `GetCfgRow` `FlushCfgRow` `RmCfgRows` `StartCfgRows` `StopCfgRows` `ClearTaskProgress` `BatchClearTaskProgress` `GetThreadId` `GetMessageId` `GetMessageUser` `GetBackupFiles` `RestoreCfg` `FreeDownloadUrl` `ImportFiles` `StopImportFiles` `ExportMd5` `DelChatMd5` `MoveSrcDirs` `ReBuildSrcDirs` `GetOptimizeSizeCfg` `FlushOptimizeSizeCfg` `GetSrcSubDirs` `GetMsgLocalDir` `GetAlLMd5Chats` `MsgRenewBatch`

### 1.6 `button_bot_web_req` — 按钮机器人服务（7）

事件总线 `button_bot_ws_bus`，页面 `/btn-bot`。

`Ping` `GetCfg` `FlushCfg` `GetBackupFiles` `RestoreCfg` `StartBot` `StopBot`

## 2. 关键动作的 payload 形态

| 动作 | value |
| --- | --- |
| `SendPhone` / `SendAuthCode` / `SendPassword` | 字符串 |
| `FlushUiProxies` | `[{"enabled":true,"server":"127.0.0.1","port":10808,"user_name":"","password":"","secret":"","tp":"http"}]` |
| `StartCfgRows` / `StopCfgRows` / `RmCfgRows` | **i64 数组**，如 `[1,3]`。传 `[[1,1]]` 会报 `invalid type: sequence, expected i64` |
| `SetHdPwd` / `UpgradeHd` | `{"old_hd":"…","raw_pwd":"…"}` |
| `FlushAntConfig` | `{"api_id":"…","api_hash":"…","req_limit":35,"phone":"+86…","hide_phone":false,"proxy":null}` |
| `RegexReplace` | `{"body":"…","regex_expr":"…","replace_str":"…"}` |
| `TestReplaceBatch` | `{"body":"…","replaces":[…]}` |
| `TestMarkdown` | `{"body":"…"}` |
| `SendMessage` | `{"cid":-100…,"body":"…"}` |

## 3. 事件总线（WS）常见事件

| 总线 | 事件 | 载荷 |
| --- | --- | --- |
| `td_login_ws_bus` | `IsVip` | `{"module_id":0,"is_vip":true}`（**只在登录/变化时推一次**） |
| | `HDVerify` | `{"signature","list","has_set_hd_pwd","local_expired","has_visited_net"}` |
| | `LoginSuccess` / `Logout` | 登录态 |
| | `NetStatus` / `TdlibReqSpeed` / `DiskFree` | 网络 / 速率 / 磁盘 |
| | `AskAuthCode` / `AskPhone` / `AskPassword` | 登录交互 |
| | `AccountRetryAfter` / `CrawlerPhoneStar` | 账号限流 |
| | `LogX` / `LogXDetail` | 后端日志镜像 |
| | `MyChats` / `MyChatsFull` | 会话列表 |
| | `Version` / `UiCfg` | 版本 / UI 配置 |
| `ecr_td_ws_bus` | `LogX` / `LogXDetail` / `RunningTask` / `TaskStats` … | 任务状态与日志 |
| `ecc_td_ws_bus` | 同上 | |
| `replace_td_ws_bus` | 同上 | |
| `va_td_ws_bus` | 同上 | |
| `button_bot_ws_bus` | `LogX` / `Status` | |

`webui/wsbridge.py` 不做白名单：任何 `bus.Event` 都会进环形缓冲并经 SSE 下发，所以后端新增事件不需要改前端。

## 4. 一致性自检

```bash
# 1) 静态：通道/动作/页面归属是否自洽
python -m webui.parity

# 2) 动态：拿后端真实的 serde 枚举与声明做集合比对
python scripts/verify_parity.py "C:\Program1\caijimao430\caijimao430\app"

# 3) 运行时：是否有动作没有任何入口
curl -s http://127.0.0.1:8080/api/parity -b cookies.txt
```

三项都通过 = 契约与实现一致。
