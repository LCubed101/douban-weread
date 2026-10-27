#!/bin/zsh
# macOS local-only Douban Cookie updater. Never commit .env or credentials.
set -u
MAIN="$HOME/douban-weread"
ENVFILE="$MAIN/.env"
PYTHON="$MAIN/.venv/bin/python"
SERVICE="gui/$(id -u)/com.lcubed.douban-weread.feishu"
echo "=== 更新豆瓣 Cookie（仅在本机操作）==="
if [[ ! -f "$ENVFILE" || ! -x "$PYTHON" ]]; then
  echo "找不到 $ENVFILE 或项目虚拟环境。未修改任何文件。"
  read '?按回车退出...'
  exit 1
fi
"$PYTHON" - "$ENVFILE" "$MAIN" <<'PY'
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

env_path, main = Path(sys.argv[1]), Path(sys.argv[2])
python = str(main / ".venv/bin/python")
original = env_path.read_text(encoding="utf-8")
lines = original.splitlines(keepends=True)
matches = [(i, m) for i, line in enumerate(lines)
           if (m := re.match(r"^(\s*(?:export\s+)?DOUBAN_COOKIE\s*=)", line))]
if len(matches) != 1:
    print("DOUBAN_COOKIE 配置项不存在或重复。未修改配置。")
    sys.exit(1)
dialog = ('display dialog "请粘贴豆瓣 Cookie（输入内容隐藏）" '
          'default answer "" with hidden answer '
          'buttons {"取消", "继续"} default button "继续" '
          'with title "更新豆瓣 Cookie"')
response = subprocess.run(["/usr/bin/osascript", "-e", dialog],
                          capture_output=True, text=True)
if response.returncode or "text returned:" not in response.stdout:
    print("已取消。")
    sys.exit(1)
cookie = response.stdout.split("text returned:", 1)[1].strip()
if cookie.lower().startswith("cookie:"):
    cookie = cookie.split(":", 1)[1].strip()
if ("\n" in cookie or "\r" in cookie or
        not re.search(r"(?:^|;)\s*dbcl2=", cookie) or
        not re.search(r"(?:^|;)\s*ck=", cookie)):
    print("Cookie 格式不正确：需要完整的 dbcl2 和 ck 字段。未修改配置。")
    sys.exit(1)

# Validate the proposed credential in child process without changing .env.
check_env = os.environ.copy()
check_env["DOUBAN_COOKIE"] = cookie
for args in (["auth", "diagnose"], ["auth", "check"]):
    result = subprocess.run([python, "-m", "douban_weread", *args],
                            cwd=main, env=check_env, capture_output=True, text=True)
    # Avoid printing raw provider responses; only show pass/fail.
    if result.returncode != 0:
        print("认证检查失败（" + " ".join(args) + "）。原配置未修改。")
        sys.exit(1)
print("豆瓣 Cookie 结构检查和只读认证检查均通过。")

index, match = matches[0]
value = "'" + cookie.replace("'", "'\\''") + "'"
newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
lines[index] = match.group(1) + value + newline
backup = env_path.with_name(".env.cookie-backup")
if backup.exists():
    print("已有备份 .env.cookie-backup。为避免覆盖，请先处理旧备份。未修改配置。")
    sys.exit(1)
fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as out:
    out.write(original)
fd, tmp = tempfile.mkstemp(prefix=".env.cookie-", dir=env_path.parent)
try:
    os.fchmod(fd, stat.S_IMODE(env_path.stat().st_mode) & 0o600 or 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write("".join(lines))
    os.replace(tmp, env_path)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print("已更新本机 .env；旧配置备份在 .env.cookie-backup。")
PY
result=$?
if [[ "$result" -ne 0 ]]; then
  echo "没有重启飞书 Bot。"
  read '?按回车退出...'
  exit "$result"
fi
read 'ANSWER?是否重启当前 PR77 飞书 Bot？输入 YES 确认：'
if [[ "$ANSWER" == "YES" ]]; then
  launchctl kickstart -k "$SERVICE"
  launchctl print "$SERVICE" | grep -E 'state =|pid =|last exit code' || true
else
  echo "已更新 Cookie，但没有重启 Bot。"
fi
read '?按回车关闭...'
