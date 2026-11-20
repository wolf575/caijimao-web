#!/usr/bin/env bash
# 容器入口：先拉起 Windows 后端（Wine），再起 Web 控制台。
#
# 两个目录分工明确：
#   /app        镜像层：crawler2.exe + 依赖 DLL + ffmpeg.exe（只读种子，不挂载）
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
HTTP_PORT="${CJ_BACKEND_HTTP_PORT:-3334}"
WS_PORT="${CJ_BACKEND_WS_PORT:-3333}"

log() { printf '[entrypoint] %s\n' "$*" >&2; }

mkdir -p "$DATA_DIR" "$APP_DIR/logs" "$APP_DIR/sled"

# ---- 播种「数据侧」的静态文件（配置、版本号） ----
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

# ---------------------------------------------------------------- 配置自愈
# 这是踩过的坑：host-cfg.json 里端口写成 0 时，后端能启动但一个端口都不监听，
# 之后永远健康检查失败、登录报「后端错误」，只能手工改文件才能救回来。
# 所以每次启动前都把这两个文件校验一遍，坏了就备份并重写成正确值。
sanitize_host_cfg() {
  local f="$APP_DIR/host-cfg.json"
  local want
  want=$(printf '{"http_port":%s,"ws_port":%s,"name":""}' "$HTTP_PORT" "$WS_PORT")
  if [ ! -f "$f" ]; then
    printf '%s\n' "$want" > "$f"
    log "生成 host-cfg.json: $want"
    return
  fi
  local http ws
  http=$(sed -n 's/.*"http_port"[[:space:]]*:[[:space:]]*\(-\{0,1\}[0-9]\+\).*/\1/p' "$f" | head -n1)
  ws=$(sed -n 's/.*"ws_port"[[:space:]]*:[[:space:]]*\(-\{0,1\}[0-9]\+\).*/\1/p' "$f" | head -n1)
  case "${http:-x}" in
    ''|*[!0-9]*) http=0 ;;
  esac
  case "${ws:-x}" in
    ''|*[!0-9]*) ws=0 ;;
  esac
  if [ "$http" -lt 1 ] || [ "$http" -gt 65535 ] || [ "$ws" -lt 1 ] || [ "$ws" -gt 65535 ]; then
    local bak="$DATA_DIR/host-cfg.bad.$(date +%Y%m%d-%H%M%S).json"
    cp -f "$f" "$bak" 2>/dev/null || true
    printf '%s\n' "$want" > "$f"
    log "host-cfg.json 端口非法(http=${http} ws=${ws})，已备份到 $bak 并重写为 $want"
  fi
}

sanitize_ui_cfg() {
  local f="$APP_DIR/ui-cfg.yml"
  if [ ! -f "$f" ]; then
    printf "api_id: ''\napi_hash: ''\nreq_limit: 35\nphone: ''\nhide_phone: false\nproxy: null\n" > "$f"
    log "生成默认 ui-cfg.yml"
    return
  fi
  # req_limit 必须 > 0，否则 Telegram 请求会被限速卡死；phone 不能只有 '+'
  local lim
  lim=$(sed -n "s/^req_limit:[[:space:]]*\([0-9]\+\).*/\1/p" "$f" | head -n1)
  case "${lim:-x}" in
    ''|*[!0-9]*) lim=0 ;;
  esac
  if [ "$lim" -lt 1 ]; then
    local bak="$DATA_DIR/ui-cfg.bad.$(date +%Y%m%d-%H%M%S).yml"
    cp -f "$f" "$bak" 2>/dev/null || true
    {
      printf "api_id: ''\napi_hash: ''\nreq_limit: 35\nphone: ''\nhide_phone: false\nproxy: null\n"
    } > "$f"
    log "ui-cfg.yml 的 req_limit 非法(${lim})，已备份到 $bak 并重写默认值"
  fi
}

sanitize_ui_proxy() {
  local f="$APP_DIR/ui-proxy.yml"
  if [ ! -f "$f" ]; then
    printf '[]\n' > "$f"
    log "生成默认 ui-proxy.yml（空代理列表；如需代理请在 TD 登录页填写）"
  fi
}

sanitize_host_cfg
sanitize_ui_cfg
sanitize_ui_proxy

# 上次异常退出可能留下 WAL/SHM，交给 sqlite 自己恢复；这里只清理锁残留
for d in "$APP_DIR"/*-data; do
  [ -d "$d" ] || continue
  rm -f "$d"/*.db-journal 2>/dev/null || true
done

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

# 监督后端：挂了就重启；Web 挂了就整体退出（由容器策略重启）。
# 重启前先 wineserver -k，避免残留的 wineserver 让新进程拿不到前缀。
restarts=0
while true; do
  if ! kill -0 "$web_pid" 2>/dev/null; then
    log "Web 控制台退出，容器随之退出"
    kill -TERM "$backend_pid" 2>/dev/null || true
    wineserver -k 2>/dev/null || true
    exit 1
  fi
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    restarts=$((restarts + 1))
    log "后端退出，${BACKEND_RESTART_DELAY}s 后重启（第 ${restarts} 次）"
    wineserver -k 2>/dev/null || true
    sleep "$BACKEND_RESTART_DELAY"
    start_backend
  fi
  sleep 2
done
