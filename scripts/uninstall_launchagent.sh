#!/bin/zsh
set -euo pipefail

LABEL="com.lcubed.douban-weread.feishu"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
DOMAIN="gui/$(id -u)"

launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
rm -f "${PLIST_PATH}"

echo "Stopped and removed ${LABEL}"
echo "Local logs were kept under ${HOME}/Library/Logs/douban-weread"
