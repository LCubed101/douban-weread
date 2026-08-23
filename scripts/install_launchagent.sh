#!/bin/zsh
set -euo pipefail

REPO_DIR="${0:A:h:h}"
HOME_DIR="${HOME}"
LABEL="com.lcubed.douban-weread.feishu"
PLIST_DIR="${HOME_DIR}/Library/LaunchAgents"
LOG_DIR="${HOME_DIR}/Library/Logs/douban-weread"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"
RUNNER_PATH="${REPO_DIR}/scripts/run_feishu_bot.sh"

mkdir -p "${PLIST_DIR}" "${LOG_DIR}"

if [[ ! -x "${RUNNER_PATH}" ]]; then
  chmod +x "${RUNNER_PATH}"
fi

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${RUNNER_PATH}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/bot.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/bot.error.log</string>
</dict>
</plist>
EOF

plutil -lint "${PLIST_PATH}"

DOMAIN="gui/$(id -u)"
launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "${DOMAIN}" "${PLIST_PATH}"
launchctl enable "${DOMAIN}/${LABEL}"
launchctl kickstart -k "${DOMAIN}/${LABEL}"

echo "Installed and started ${LABEL}"
echo "LaunchAgent: ${PLIST_PATH}"
echo "Logs: ${LOG_DIR}/bot.log and ${LOG_DIR}/bot.error.log"
