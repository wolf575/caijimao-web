# 功能对照表（Parity）

目标：桌面版能做的每一件事，Web 版都能做；Web 版能做的，都是桌面版本来就有的（除了登录认证和 API 控制台）。

## 1. 逐页对照

| 桌面版位置 | Web 版 | 后端通道 | 状态 |
| --- | --- | --- | --- |
| 用户注册信息（VIP 授权页） | `/` 的「VIP 模块」卡 | `td_web_req.GetLease/GetHD` | ✅ 只读展示；本版本已解除限制，此栏仅观测 |
| 服务状态栏（后台/TD/网络/速度/磁盘） | `/` 的「实时事件」卡 | `td_login_ws_bus` | ✅ 走 SSE 实时刷新 |
| 五个服务的启动/停止/任务统计 | `/` 的「服务控制」+ 各自详情页 | 各 `*_td_web_req` | ✅ |
| TD 登录（手机号 / 验证码 / 两步密码） | `/td-login` | `SendPhone/SendAuthCode/SendPassword` | ✅ |
| 代理设置对话框 | `/td-login` 的「代理配置」 | `FlushUiProxies` | ✅ 直接编辑 JSON 数组 |
| 会话列表 / 加入群 / 批量退出 | `/td-login` | `GetMyChatsFull/JoinChat/BatchExitChat` | ✅ |
| TD 爬虫服务（爬虫PRO）配置表 | `/ecr` | `ecr_td_web_req.GetCfg/GetCfgRow/StartCfgRows` | ✅ 表格 + 每行启停 |
| 频道群克隆PRO 配置表 | `/ecc` | `ecc_td_web_req.*` | ✅ |
| 批量替换/删除服务 | `/replace` | `replace_td_web_req.*` | ✅ |
| 付费群助手（媒体加工） | `/va` | `va_td_web_req.*` | ✅ 含导入/导出/目录重建 |
| 按钮机器人服务 | `/btn-bot` | `button_bot_web_req.*` | ✅ 需先配 token |
| 全局设置（编码器 / ffmpeg / sqlite / 文件名替换 / 主机配置） | `/settings` | `td_web_req.*` | ✅ |
| 授权迁移 / 客户保护密码 | `/settings` 的「客户授权」 | `SetHdPwd/UpgradeHd` | ✅ |
| 日志窗口 | `/logs?kind=sys\|err` | 读 `app/logs/*.log` | ✅ 3 秒自动刷新 |
| 各页底部的「高级动作」区 | 每个服务页 | 该通道剩余动作 | ✅ 后端有的动作都能点到 |
| —（桌面版没有） | `/admin/console` | 任意通道任意动作 | ➕ 新增，用于穷尽与排障 |

## 2. 数字对账

| 通道 | 动作数 | 专属页面 | 仅控制台 |
| --- | --- | --- | --- |
| `td_web_req` | 38 | 37 | 1（`None`） |
| `ecr_td_web_req` | 25 | 25 | 0 |
| `ecc_td_web_req` | 28 | 28 | 0 |
| `replace_td_web_req` | 9 | 9 | 0 |
| `va_td_web_req` | 31 | 31 | 0 |
| `button_bot_web_req` | 7 | 7 | 0 |
| **合计** | **138** | **137** | **1** |

## 3. 怎么验证

```bash
# 静态自洽
python -m webui.parity
# → channels=6 actions=138 console_only=1 OK

# 与后端真实枚举比对（会读 app/logs/err.*.log）
python scripts/verify_parity.py "C:\Program1\caijimao430\caijimao430\app"
# → 六个通道逐行 [OK]  live==declared

# 运行时是否有动作没有入口
curl -s -b cookies.txt http://127.0.0.1:8080/api/parity
# → {"ok":true,"channels":6,"actions":138,"problems":[],"console_only":[["td_web_req","None"]]}
```

## 4. 实测记录（4.3.0，本地）

| 验证项 | 结果 |
| --- | --- |
| 未登录访问 `/` | 303 → `/login` |
| 错误密码 | 401 + 限速计数 |
| 正确密码 | 303 + `cj_session` |
| 全部 10 个页面 | 200 |
| `td_web_req.GetVersion` | `{"version":"4.3.0"}` |
| `ecr_td_web_req.GetCfg` | 真实 rulers JSON |
| `ecr_td_web_req.StartService` | `ok`，后端日志出现 `✅ 爬取服务已经启动......` |
| `ecc_td_web_req.StartService` | `ok`，`[克隆PRO] 心跳检测` + `loop-task-main-*` |
| 未声明动作 | 400 `{"ok":false,"error":"unknown action"}` |
| SSE | `event: hello` 快照 + `event: event` 逐条推送 |
| 后端 VIP 拒绝行 | 0 条 |

## 5. 不追求等价的部分

这些是**客户端形态**的差异，不是功能缺失：

- 桌面版是单窗口树形导航；Web 版是左侧栏 + 多页面。信息层级一一对应。
- 桌面版有系统托盘、开机自启；Web 版没有（容器里没有桌面会话）。
- 桌面版能「最小化到托盘继续跑」；Web 版后端始终在跑，关掉浏览器不影响任务。
- Web 版多了账号密码登录和 `/admin/console`。前者是需求要求的，后者是验证工具。
