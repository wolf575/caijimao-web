#!/usr/bin/env bash
# 从 GitHub Release 拉取 payload（Windows 后端 + 依赖 DLL）。
#
#   ./scripts/fetch_payload.sh            # 默认 4.3.0
#   VERSION=4.3.0 REPO=wolf575/caijimao-web ./scripts/fetch_payload.sh
#
# 结果：
#   payload/app/crawler2.exe
#   payload/app/lib/*.dll
#   payload/app/{config.yml,ver}
#
# ffmpeg.exe 不随 Release 分发（体积原因），见 README「准备 ffmpeg」。
set -euo pipefail

REPO="${REPO:-wolf575/caijimao-web}"
VERSION="${VERSION:-4.3.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSET="caijimao-${VERSION}-payload.zip"
URL="https://github.com/${REPO}/releases/download/v${VERSION}/${ASSET}"

mkdir -p "$ROOT/payload"
if [ -f "$ROOT/payload/app/crawler2.exe" ]; then
  echo "payload 已存在，跳过下载：$ROOT/payload/app/crawler2.exe"
else
  echo "下载 $URL"
  if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 -o "$ROOT/payload/$ASSET" "$URL"
  else
    wget -O "$ROOT/payload/$ASSET" "$URL"
  fi
  ( cd "$ROOT/payload" && unzip -q -o "$ASSET" && rm -f "$ASSET" )
fi

if [ ! -f "$ROOT/payload/app/ffmpeg.exe" ]; then
  cat >&2 <<'EOF'

[注意] payload/app/ffmpeg.exe 缺失。
FFmpeg 体积约 95 MB，未放进 Release。请自行下载后放到 payload/app/ffmpeg.exe：
  https://www.gyan.dev/ffmpeg/builds/  ->  ffmpeg-release-essentials.zip
  unzip 后取 bin/ffmpeg.exe
EOF
fi

echo "完成：$ROOT/payload"
ls -la "$ROOT/payload/app" 2>/dev/null || true
