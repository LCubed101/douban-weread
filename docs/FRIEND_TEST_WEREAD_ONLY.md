# 朋友试用：WeRead-only 私有部署

这份指南用于 **flomo / 书单截图 → 飞书 Bot → 微信读书链接** 的朋友试用场景。

目标：每位试用者使用自己的飞书应用、自己的微信读书 API Key、自己的电脑运行 Bot。**不需要豆瓣账号，不需要 `DOUBAN_COOKIE`。**

> 隐私说明：截图 OCR 使用 RapidOCR 在本机处理，不调用 OpenAI / Claude / Kimi。飞书消息仍会经过试用者自己的飞书应用；微信读书查询使用试用者自己的官方 API Key。

## 试用范围

开启 `ROUTER_MODE=weread_only` 后：

```text
单独书名 / flomo AI 洞察 / 书单截图
→ 发给自己的 Feishu Bot
→ 文本直接取书名，截图本地 OCR 提取《书名》
→ 查询微信读书
→ 可读书返回按钮
→ 未找到的书进入 Waiting List，之后重新搜索
```

这轮朋友测试 **完全不走豆瓣路径**。

## 1. 准备环境

需要：

- macOS（当前朋友试用优先）
- Python 3.10+
- Git
- 一个自己的飞书账号 / 飞书自建应用
- 一个自己的微信读书官方 Agent API Key

## 2. 下载项目

终端执行：

```bash
git clone https://github.com/LCubed101/douban-weread.git
cd douban-weread
git checkout agent/weread-shelf-baseline
```

创建 Python 环境并安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

## 3. 创建自己的飞书 Bot

在飞书开放平台创建 **企业自建应用**，启用机器人能力。

需要完成：

1. 记录自己的 `App ID` 和 `App Secret`；
2. 允许机器人接收消息、发送消息 / 卡片、读取消息中的图片资源；
3. 在事件订阅中选择 **长连接 / WebSocket**；
4. 添加事件 `im.message.receive_v1`；
5. 发布应用，并确保自己的飞书账号在可用范围内。

详细步骤见 [FEISHU_SETUP.md](FEISHU_SETUP.md)。

## 4. 获取自己的微信读书 API Key

打开微信读书官方 Agent API Key 页面：

```text
https://weread.qq.com/r/weread-skills
```

使用自己的微信读书账号获取个人 `WEREAD_API_KEY`。

这个试用流程不需要微信读书 Cookie，也不需要豆瓣 Cookie。

## 5. 配置 `.env`

项目目录执行：

```bash
cp .env.example .env
```

朋友只需要填写：

```env
FEISHU_APP_ID='自己的 App ID'
FEISHU_APP_SECRET='自己的 App Secret'
ROUTER_MODE=weread_only
WEREAD_API_KEY='自己的 WeRead API Key'
DATABASE_URL='sqlite:///data/douban-weread.db'
DOUBAN_COOKIE=
```

关键是：

```env
ROUTER_MODE=weread_only
```

开启后，Bot 不会把单独书名送进 Douban-first 流程，也不需要豆瓣凭证。

不要把 `.env` 发给其他人，也不要提交到 GitHub。

## 6. 先测试微信读书 API

加载环境变量：

```bash
set -a
source .env
set +a
```

执行只读搜索：

```bash
douban-weread weread search "专注" --limit 5
```

如果能返回微信读书候选，说明 `WEREAD_API_KEY` 正常。

## 7. 第一次启动 Feishu Bot

仍在项目目录：

```bash
set -a
source .env
set +a

douban-weread-feishu
```

启动日志应包含：

```text
Router mode: weread_only
WeRead-only mode enabled.
```

看到 WebSocket 已连接后，回到飞书。

建议做两个测试：

1. 直接发送一个书名，例如 `专注`；
2. 把一张 flomo AI 洞察 / 书单推荐截图直接发给 Bot。

理想结果：

- 单书直接返回微信读书处理结果，不出现豆瓣候选；
- 多书截图返回一张「书单处理结果」卡；
- 可读书有「打开《书名》」按钮；
- 未找到的书会自动记住，并进入 Waiting List。

前台运行时按 `Control + C` 停止。

## 8. macOS 后台运行

前台测试正常后：

```bash
zsh scripts/install_launchagent.sh
```

检查：

```bash
launchctl print gui/$(id -u)/com.lcubed.douban-weread.feishu | grep -E 'state =|pid =|runs =|last exit code'
```

看到：

```text
state = running
```

说明 Bot 已经在后台运行，并会在 macOS 登录后自动启动。

以后代码更新后，记得：

```bash
cd ~/douban-weread
git checkout agent/weread-shelf-baseline
git pull
launchctl kickstart -k gui/$(id -u)/com.lcubed.douban-weread.feishu
```

## 9. 朋友测试时只需要知道这一句话

> 直接发书名，或者把 flomo 的书单推荐截图发给 Bot 就行。

不要先解释 Waiting List、OCR、匹配算法。让第一次使用尽量自然；哪里看不懂、哪里想点却找不到按钮，直接截图反馈即可。

## 当前限制

- 微信读书官方 Agent API 是只读接口，项目不会声称能自动加入书架。
- 微信读书 App 中能看到的「待上架」书，不一定会出现在 Agent API 搜索结果里。
- 截图提取目前优先识别明确的 `《书名》`；如果图片里没有稳定识别到书名号，Bot 会请用户换图或直接发送书名。
