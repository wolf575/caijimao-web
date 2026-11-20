#!/usr/bin/env bash
# 一条命令拉起采集猫 Web 版（单容器：Wine 跑原版后端 + FastAPI 控制台）
#
#   ./scripts/run.sh '你的密码'
#   WEB_PASSWORD='你的密码' ./scripts/run.sh
#   PORT=18080 DATA_DIR=/srv/cjdata ./scripts/run.sh '你的密码'
#
# 只做三件事：拉镜像（如缺）、建数据目录、run。重复执行是安全的（先删旧容器）。
set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/wolf575/caijimao-web:4.3.0}"
NAME="${NAME:-caijimao-web}"
PORT="${PORT:-8080}"
DATA_DIR="${DATA_DIR:-$PWD/data}"
WEB_USER="${WEB_USER:-admin}"
WEB_PASSWORD="${1:-${WEB_PASSWORD:-}}"
SECRET_KEY="${SECRET_KEY:-}"

if [ -z "$WEB_PASSWORD" ]; then
  echo "用法: $0 '你的密码'   （或用环境变量 WEB_PASSWORD=… ）" >&2
  exit 2
fi

# 没给 SECRET_KEY 就固定生成一次并存到数据目录，重启后会话不失效
if [ -z "$SECRET_KEY" ]; then
  KEY_FILE="$DATA_DIR/.secret_key"
  if [ -f "$KEY_FILE" ]; then
    SECRET_KEY="$(cat "$KEY_FILE")"
  else
    mkdir -p "$DATA_DIR"
    SECRET_KEY="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    printf '%s' "$SECRET_KEY" > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
  fi
fi

mkdir -p "$DATA_DIR"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo ">> 拉取镜像（约 5.4 GB，首次会比较久）"
  docker pull "$IMAGE"
fi

docker rm -f "$NAME" >/dev/null 2>&1 || true

echo ">> 启动 $NAME  →  http://<本机IP>:$PORT   数据目录 $DATA_DIR"
docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  -p "${PORT}:8080" \
  -e "WEB_USER=${WEB_USER}" \
  -e "WEB_PASSWORD=${WEB_PASSWORD}" \
  -e "SECRET_KEY=${SECRET_KEY}" \
  -e "TZ=${TZ:-Asia/Shanghai}" \
  -v "${DATA_DIR}:/data" \
  --shm-size=512m \
  --ulimit nofile=65535:65535 \
  "$IMAGE"

echo ">> 首次启动要初始化 Wine prefix，约 20~60 秒后变 healthy"
echo "   docker ps --filter name=$NAME"
echo "   docker logs -f $NAME"
