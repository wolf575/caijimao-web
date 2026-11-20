# 第三方组件与声明

本仓库**不包含**任何第三方软件的源代码。它只包含：

1. 一份 Python 编写的 Web 控制台（`webui/`），MIT 许可，本仓库原创。
2. 一组字节级补丁脚本（`patch/`），MIT 许可，本仓库原创。
3. 文档与截图。

`payload/`（不在 git 里，通过 GitHub Release 分发）与运行期由用户自行提供的文件属于第三方：

| 文件 | 说明 | 权利归属 |
| --- | --- | --- |
| `crawler2.exe` | 采集猫 4.3.0 后端（Rust + TDLib），已打三个字节补丁 | 原作者 |
| `lib/tdjson.dll` | Telegram TDLib 1.8.59 | Telegram FZ-LLC，Apache-2.0 |
| `lib/libcrypto-3-x64.dll`、`lib/libssl-3-x64.dll` | OpenSSL 3 | OpenSSL 项目，Apache-2.0 |
| `lib/zlib1.dll` | zlib | Jean-loup Gailly & Mark Adler，zlib 许可 |
| `ffmpeg.exe` | FFmpeg 8.0.1 essentials（gyan.dev 构建） | FFmpeg 项目，LGPL/GPL |

运行期 Python 依赖见 `requirements.txt`，均为公开发布的开源包（FastAPI / Starlette / uvicorn / httpx / Jinja2 / bcrypt / itsdangerous / websockets / python-multipart）。

## 关于补丁

`patch/patch4.py` 只做一件事：把后端里三个 VIP 判定函数改成立即返回常量，从而让本机运行时不再走「未开通该服务的 vip 功能」的分支。它**不修改**任何网络通讯、不伪造授权、不绕过 Telegram 自身的限制。补丁只在本地你自己的副本上生效，修改后的二进制由你自己保管。

如果你是该软件的版权方并认为本仓库不妥，请开 issue 联系，我会配合下架相关内容。
