# 采集猫 Web 版镜像
#
# 思路：业务逻辑全部在 Windows 后端 crawler2.exe 里（Rust + TDLib），
# 桌面版 PySide6 只是它的 HTTP/WS 客户端。所以这里用 Wine 跑原版后端，
# 用 FastAPI 重写「客户端」这一层 —— 功能因此天然一一对应。
#
# 构建上下文必须是仓库根目录：
#   docker build -f docker/Dockerfile -t caijimao-web:4.3.0 .
#
# 需要的 payload/（从 GitHub Release 解压而来）：
#   payload/app/crawler2.exe
#   payload/app/ffmpeg.exe
#   payload/app/lib/{tdjson.dll,libcrypto-3-x64.dll,libssl-3-x64.dll,zlib1.dll}
#   payload/app/{config.yml,ver}

FROM debian:bookworm-slim

# OCI 标签：把镜像和仓库关联起来（GHCR 靠 org.opencontainers.image.source 自动建链接，
# 有了链接之后包的可见性才能跟随仓库）
LABEL org.opencontainers.image.title="caijimao-web" \
      org.opencontainers.image.description="采集猫 4.3.0 Web 版：Wine 跑原版 Rust 后端 + FastAPI 控制台" \
      org.opencontainers.image.source="https://github.com/wolf575/caijimao-web" \
      org.opencontainers.image.url="https://github.com/wolf575/caijimao-web" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="4.3.0"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WINEDEBUG=-all \
    WINEPREFIX=/wine \
    WINEARCH=win64 \
    XDG_RUNTIME_DIR=/tmp/runtime \
    CJ_EXE_DIR=/app \
    CJ_APP_DIR=/data/app \
    CJ_DATA_DIR=/data \
    CJ_BACKEND_HTTP=http://127.0.0.1:3334 \
    CJ_BACKEND_WS=ws://127.0.0.1:3333/ws

# ---------------------------------------------------------------------------
# Wine：必须用 WineHQ 的 stable（>= 9），不能用 Debian 自带的 8.0。
# 原因：后端是 Rust 程序，getrandom 会静态导入 bcryptprimitives.dll
# （BCryptGenRandom / ProcessPrng），而 Debian bookworm 的 wine 8.0
# 没有提供这个 DLL，进程会在 LdrInitializeThunk 阶段就
# c0000135 (STATUS_DLL_NOT_FOUND) 退出，日志里一行都不留。
# ---------------------------------------------------------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg xz-utils \
 && printf 'Acquire::Retries "6";\nAcquire::http::Timeout "45";\nAcquire::https::Timeout "45";\n' \
      > /etc/apt/apt.conf.d/80-retries \
 && mkdir -pm755 /etc/apt/keyrings \
 && curl -fsSL https://dl.winehq.org/wine-builds/winehq.key \
      -o /etc/apt/keyrings/winehq-archive.key \
 && curl -fsSL https://dl.winehq.org/wine-builds/debian/dists/bookworm/winehq-bookworm.sources \
      -o /etc/apt/sources.list.d/winehq-bookworm.sources \
 && dpkg --add-architecture i386 \
 && apt-get update \
 && apt-get install -y --no-install-recommends winehq-stable \
 && apt-get purge -y gnupg xz-utils \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# Python + 运行期依赖
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-venv python3-pip \
      tini tzdata libfreetype6 libfontconfig1 \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /srv
COPY requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r /srv/requirements.txt

# ---- 后端 payload（Windows PE）----
# /app 是「程序」目录（镜像层，只读语义）：exe + 依赖 DLL + ffmpeg.exe。
# 后端的「数据」目录是卷里的 $CJ_APP_DIR（默认 /data/app），由 entrypoint 建好。
# 两者分开是必须的：Docker Desktop 在 Windows 上把卷映射成 virtiofs，
# Wine 无法从那里启动 57 MB 的 PE（rc=5，无任何输出）。
COPY payload/app /app

# Windows 加载器只在「exe 所在目录」找依赖 DLL，不会递归进 lib/。
# 原版靠 start2.bat 把 lib 塞进 PATH；这里更稳的做法是把 DLL 放到 exe 旁边，
# 同时保留 lib/ 并把 <app>/lib 加进 WINEPATH 作为兜底。
RUN cp -f /app/lib/*.dll /app/ && ls -l /app/*.dll

# ---- Web 控制台 ----
COPY webui /srv/webui
COPY scripts /srv/scripts
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 预初始化 Wine prefix，避免每次启动都做一次（镜像里做一次即可）
RUN mkdir -p /wine /data \
 && wineboot --init >/dev/null 2>&1 || true \
 && wineserver -w || true

EXPOSE 8080

HEALTHCHECK --interval=20s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
