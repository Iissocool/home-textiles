#!/bin/bash
# OpenCLI 自启动 — 在 Chromium 中加载 OpenCLI 扩展
# 放在 ~/.config/autostart/ 或手动运行

chromium \
  --show-component-extension-options \
  --enable-gpu-rasterization \
  --no-default-browser-check \
  --disable-pings \
  --media-router=0 \
  --enable-remote-extensions \
  --load-extension=/home/weng/.local/share/opencli-extension \
  --window-size=1280,800 \
  --new-window about:blank &

# 等待扩展连接
for i in $(seq 1 20); do
  sleep 2
  if opencli doctor 2>/dev/null | grep -q "Extension: connected"; then
    echo "✅ OpenCLI connected after $((i * 2))s"
    exit 0
  fi
done
echo "⚠️ OpenCLI 连接超时，手动检查: opencli doctor"
