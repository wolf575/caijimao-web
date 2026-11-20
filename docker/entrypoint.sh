#!/usr/bin/env bash
# 容器入口：先拉起 Windows 后端（Wine），再起 Web 控制台。
#
# 两个目录分工明确：
#   /app        镜像层：crawler2.exe + 依赖 DLL + ffmpeg.exe（只读种子，不挂卷）
#   $CJ_APP_DIR 卷层：后端的工作目录（config.yml / logs / sled / data）
#
# 为什么 exe 必须留在镜像层：Docker Desktop 在 Windows 上把 /data 映射成
# virtiofs，Wine 无法从那里 mmap 并启动 57 MB 的 PE（直接 rc=5，连一行输出都没有）。
# 所以「程序」放镜像、「数据」放卷：wine 用绝对路径启动镜像层的 exe，
# 但 cwd 指向卷 —— 后端的 config/logs/data/sled 就都落进卷里，
# 重启容器不用重新登录 Telegram。
set -uo pipefail

EXE_DIR="${CJ_EXE_DIR:-/app}"
APP_DIR="${CJ_APP_DIR:-/data/app}"
DATA_DIR="${CJ_DATA_DIR:-/data}"
WEB_PORT="${WEB_PORT:-8080}"
BACKEND_RESTART_DELAY="${BACKEND_RESTART_DELAY:-3}"

log() { printf '[entrypoint] %s\n' "$*" >&2; }

mkdir -p "$DATA_DIR" "$APP_DIR/logs" "$APP_DIR/sled"

# ---- 播种「数据侧」的静态文件（配置、版本号）----
for f in config.yml ver; do
  if [ -f "$EXE_DIR/$f" ] && [ ! -f "$APP_DIR/$f" ]; then
    cp -f "$EXE_DIR/$f" "$APP_DIR/$f"
    log "播种 $f -> $APP_DIR/$f"
  fi
done
# 后端会按 cwd/lib 找 DLL（原版靠 start2.bat 设 PATH）；卷里放一份软链即可
if [ ! -e "$APP_DIR/lib" ]; then
  ln -s "$EXE_DIR/lib" "$APP_DIR/lib" 2>/dev/null || mkdir -p "$APP_DIR/lib"
fi

# 首次启动时补两份 UI 配置文件。不补的话后端会打
#   ant_config.rs:123 / ab_proxy.rs:67  read_file_error
# 而且 GetAntConfig 会返回 err，全局设置页空白。
if [ ! -f "$APP_DIR/ui-cfg.yml" ]; then
  printf "api_id: ''\napi_hash: ''\nreq_limit: 35\nphone: ''\nhide_phone: false\nproxy: null\n" \
    > "$APP_DIR/ui-cfg.yml"
  log "生成默认 ui-cfg.yml"
fi
if [ ! -f "$APP_DIR/ui-proxy.yml" ]; then
  printf '[]\n' > "$APP_DIR/ui-proxy.yml"
  log "生成默认 ui-proxy.yml（空代理列表；如需代理请在 TD 登录页填写）"
fi

# Wine 需要可写的 HOME 与 runtime dir
export HOME="${HOME:-/root}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime}"
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
export WINEPREFIX="${WINEPREFIX:-/wine}"
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-mscoree,mshtml=}"
export WINEPATH="$EXE_DIR/lib"

if [ ! -d "$WINEPREFIX/drive_c" ]; then
  log "初始化 WINEPREFIX=$WINEPREFIX"
  wineboot --init >/dev/null 2>&1 || true
  wineserver -w || true
fi

# --- 后端 ---
backend_pid=""
start_backend() {
  log "启动后端: $EXE_DIR/crawler2.exe  (cwd=$APP_DIR)"
  (
    cd "$APP_DIR" || exit 1
    exec wine "$EXE_DIR/crawler2.exe"
  ) >>"$DATA_DIR/backend.stdout.log" 2>&1 &
  backend_pid=$!
  log "后端 PID=$backend_pid"
}

# --- Web 控制台 ---
web_pid=""
start_web() {
  log "启动 Web 控制台: 0.0.0.0:$WEB_PORT"
  uvicorn webui.app:app --host 0.0.0.0 --port "$WEB_PORT" --proxy-headers \
    --log-level "${LOG_LEVEL:-info}" >>"$DATA_DIR/webui.log" 2>&1 &
  web_pid=$!
  log "Web PID=$web_pid"
}

shutdown() {
  log "收到退出信号，正在停止…"
  [ -n "${web_pid:-}" ] && kill -TERM "$web_pid" 2>/dev/null || true
  [ -n "${backend_pid:-}" ] && kill -TERM "$backend_pid" 2>/dev/null || true
  wineserver -k 2>/dev/null || true
  wait 2>/dev/null || true
  log "已停止"
  exit 0
}
trap shutdown TERM INT

cd /srv || exit 1
start_backend
start_web

# 监督后端：挂了就重启；Web 挂了就整体退出（由容器策略重启）
while true; do
  if ! kill -0 "$web_pid" 2>/dev/null; then
    log "Web 控制台退出，容器随之退出"
    kill -TERM "$backend_pid" 2>/dev/null || true
    wineserver -k 2>/dev/null || true
    exit 1
  fi
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    log "后端退出，${BACKEND_RESTART_DELAY}s 后重启"
    sleep "$BACKEND_RESTART_DELAY"
    start_backend
  fi
  sleep 2
done
