# Feishu Bot Setup

这份指南面向第一次部署 `douban-weread` 的用户，目标是让你用自己的飞书应用把机器人跑起来。

> 每个人都应该使用自己的 Feishu App ID / Secret。不要共享作者的 `.env`，也不要把真实 Secret、Cookie、Token 提交到 GitHub。

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

V1 需要完成这些能力：

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

这是飞书发送了「进入机器人私聊」一类事件，但当前项目没有为它注册处理器。只要正常的书名 / ISBN / 图片消息能够回复，这条日志可以暂时忽略。

## 5. 安装项目

```bash
git clone https://github.com/LCubed101/douban-weread.git
cd douban-weread

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

如果你还要使用豆瓣「想读」和微信读书功能，再填写：

```env
DOUBAN_COOKIE=
WEREAD_COOKIE=
```

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
Douban × WeRead Feishu Book Inbox starting via WebSocket...
FeishuChannel: bot identity resolved ...
connected to wss://msg-frontier.feishu.cn/...
```

看到 `connected to wss://...` 后，就可以回到飞书测试机器人。

停止前台机器人：

```text
Control + C
```

## 8. 做 3 个 smoke tests

建议按这个顺序测试：

1. 发一个书名，例如 `白夜行`；
2. 发一个 ISBN；
3. 发一张书籍封面图片。

预期：

- 书名可以返回豆瓣候选；
- ISBN 可以做更精确的版本匹配；
- 图片会在本机运行 OCR；
- 如果复杂封面无法可靠判断，机器人会要求你补书名、ISBN、豆瓣链接、版权页或条码页，而不是强行猜一本无关的书。

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

复杂封面识别失败并不一定代表程序异常。V1 会尽量 fail closed：无法可靠判断时要求用户补充更明确的信息。

## 11. 安全说明

不要把下面内容提交到 GitHub、Issue、截图或聊天记录：

- `FEISHU_APP_SECRET`
- `DOUBAN_COOKIE`
- `WEREAD_COOKIE`
- 其他登录态、Token、Cookie

项目的 `.env.example` 只提供字段模板；真实值请保存在本地 `.env`。

更多故障排查见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。
