# Feishu Bot Setup

这份指南面向第一次部署 `douban-weread` 的用户，目标是让你用自己的飞书应用把机器人跑起来。

> 每个人都应该使用自己的 Feishu App ID / Secret。不要共享作者的 `.env`，也不要把真实 Secret、Cookie、Token 提交到 GitHub。

如果你只想测试 **flomo / 书单截图 → 微信读书**，不使用豆瓣，请直接看 [朋友试用：WeRead-only 私有部署](FRIEND_TEST_WEREAD_ONLY.md)。

## 1. 创建飞书应用

1. 打开飞书开放平台，进入开发者后台。
2. 创建一个企业自建应用。
3. 给应用启用「机器人」能力。
4. 记录应用的 **App ID** 和 **App Secret**。

之后把它们写入本地 `.env`：

```env
FEISHU_APP_ID=你的 App ID
FEISHU_APP_SECRET=你的 App Secret
```

不要把真实值提交到 Git。

## 2. 配置机器人可用范围

在飞书开发者后台确认：

- 机器人能力已启用；
- 应用已经发布到你自己的组织 / 测试范围；
- 你的飞书账号在应用可用范围内；
- 你可以在飞书里找到并打开这个机器人。

如果机器人在飞书里完全搜不到，先检查应用是否已经发布以及可用范围是否包含当前账号。

## 3. 配置消息与资源权限

V1 / V1.1 需要完成这些能力：

- 接收用户发给机器人的消息；
- 向会话发送文本和交互卡片；
- 读取 / 下载消息中的图片资源；
- 接收交互卡片按钮操作。

飞书开放平台的权限名称可能会随语言和控制台版本变化。请在权限管理中为上述能力添加对应的即时通讯（IM）权限，并在修改权限后重新发布应用版本。

如果文字消息能收到、图片却无法处理，优先检查「读取消息资源 / 图片资源」相关权限。

## 4. 配置事件订阅

这个项目通过 **WebSocket / 长连接** 接收飞书事件，不需要你部署一个公网 webhook URL。

在飞书开放平台的「事件与回调 / 事件订阅」区域：

1. 选择长连接 / WebSocket 方式接收事件；
2. 添加接收消息事件：`im.message.receive_v1`；
3. 保存配置；
4. 如果平台要求发布新版本，重新发布应用。

项目当前会处理机器人收到的文本和图片消息。

你偶尔可能在日志中看到：

```text
processor not found, type: im.chat.access_event.bot_p2p_chat_entered_v1
```

这是飞书发送了「进入机器人私聊」一类事件，但当前项目没有为它注册处理器。只要正常消息能够回复，这条日志可以暂时忽略。

## 5. 安装项目

```bash
git clone https://github.com/LCubed101/douban-weread.git
cd douban-weread
git checkout agent/weread-shelf-baseline

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

OCR 使用 RapidOCR / ONNX Runtime，会随项目依赖一起安装，并在本机运行。

## 6. 创建 `.env`

```bash
cp .env.example .env
```

至少先填写飞书凭证：

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

微信读书功能使用腾讯官方 Agent API Key：

```env
WEREAD_API_KEY=
```

如果你还要使用豆瓣「想读」写入，再填写：

```env
DOUBAN_COOKIE=
```

**不使用豆瓣时，`DOUBAN_COOKIE` 保持空白即可。**

注意：项目当前使用的是 `WEREAD_API_KEY`，不是旧文档中的 `WEREAD_COOKIE`。

这些值只应该保存在你自己的机器上。

## 7. 第一次前台启动

第一次建议先在终端前台启动，这样最容易看到错误：

```bash
set -a
source .env
set +a

douban-weread-feishu
```

正常启动时会看到类似：

```text
Douban × WeRead Feishu Reading Inbox starting via WebSocket...
FeishuChannel: bot identity resolved ...
connected to wss://msg-frontier.feishu.cn/...
```

看到 `connected to wss://...` 后，就可以回到飞书测试机器人。

停止前台机器人：

```text
Control + C
```

## 8. 做 smoke tests

### WeRead-only 朋友试用

如果这轮不使用豆瓣，推荐只测：

1. 一张包含多个明确 `《书名》` 的 flomo / 书单截图；
2. 一段包含多个 `《书名》` 的文本；
3. 点击结果卡中的「打开《书名》」；
4. 有未找到书时，点击「查看等待列表」。

预期：

- 图片在本机运行 OCR；
- 多本书被提取后返回一张汇总卡；
- 可读书返回微信读书按钮；
- 未找到的书进入 Waiting List，之后按计划重新搜索。

当前单独发送一个普通书名仍属于旧的 Douban-first 单书流程，因此 **WeRead-only friends beta 暂时不要把单书普通文本作为测试入口**。

### 完整 Douban + WeRead 流程

如果已经配置豆瓣 Cookie，可以继续测试：

1. 发一个书名，例如 `白夜行`；
2. 发一个 ISBN；
3. 发一张单本书籍封面图片。

预期可以进入豆瓣版本确认 / 想读及微信读书匹配流程。

## 9. macOS 后台自动启动

确认前台测试正常后：

```bash
zsh scripts/install_launchagent.sh
```

它会创建并启动：

```text
com.lcubed.douban-weread.feishu
```

检查状态：

```bash
launchctl print gui/$(id -u)/com.lcubed.douban-weread.feishu \
  | grep -E 'state =|pid =|runs =|last exit code'
```

正常应看到：

```text
state = running
pid = <PID>
```

查看进程：

```bash
ps aux | grep '[d]ouban-weread-feishu'
```

查看日志：

```bash
tail -50 ~/Library/Logs/douban-weread/bot.log
tail -50 ~/Library/Logs/douban-weread/bot.error.log
```

手动重启：

```bash
launchctl kickstart -k gui/$(id -u)/com.lcubed.douban-weread.feishu
```

卸载自动启动：

```bash
zsh scripts/uninstall_launchagent.sh
```

## 10. 常见问题

### 飞书里机器人完全不回复

先检查：

```bash
launchctl print gui/$(id -u)/com.lcubed.douban-weread.feishu \
  | grep -E 'state =|pid =|runs =|last exit code'
```

如果不是 `state = running`，再检查：

```bash
ps aux | grep '[d]ouban-weread-feishu'
tail -50 ~/Library/Logs/douban-weread/bot.error.log
tail -50 ~/Library/Logs/douban-weread/bot.log
```

### `last exit code = 78: EX_CONFIG`

先确认启动脚本有可执行权限：

```bash
ls -l scripts/run_feishu_bot.sh
```

应该包含 `x`，例如：

```text
-rwxr-xr-x
```

如果没有：

```bash
chmod +x scripts/run_feishu_bot.sh
zsh scripts/install_launchagent.sh
```

### 能启动，但飞书收不到消息

确认日志里存在新的：

```text
connected to wss://msg-frontier.feishu.cn/...
```

如果已经连上但仍收不到消息，回到飞书开放平台检查：

- `im.message.receive_v1` 是否已添加；
- 是否使用长连接 / WebSocket；
- 应用权限修改后是否重新发布；
- 当前账号是否在应用可用范围。

### 图片无法识别

图片 OCR 在本地运行，不需要 OpenAI / Claude / Kimi API。先确认依赖已安装：

```bash
python3 -c "import rapidocr_onnxruntime; print('RapidOCR OK')"
```

### 微信读书搜索提示缺少凭证

确认 `.env` 中是：

```env
WEREAD_API_KEY='...'
```

不是 `WEREAD_COOKIE`。

## 11. 安全说明

不要把下面内容提交到 GitHub、Issue、截图或聊天记录：

- `FEISHU_APP_SECRET`
- `DOUBAN_COOKIE`（如果使用）
- `WEREAD_API_KEY`
- 其他登录态、Token、Cookie

项目的 `.env.example` 只提供字段模板；真实值请保存在本地 `.env`。

更多故障排查见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。
