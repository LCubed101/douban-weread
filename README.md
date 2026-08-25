# Douban × WeRead

A self-hosted **Reading Inbox / Reading Router** prototype.

> 把任何地方偶然遇到的书，低摩擦地送进你自己的阅读系统。
>
> Don't replace your system. Connect it.

当前 V1 以飞书为主要 Capture 界面：你可以发送书名、ISBN 或书籍图片，系统识别并确认 Work / Edition，然后按你的阅读习惯路由到豆瓣和微信读书。Douban 是一种可选的阅读记录路径，不是产品边界；Feishu 也是一个输入适配器，不是产品本身。

产品方向与边界见 [docs/PRODUCT_DIRECTION.md](docs/PRODUCT_DIRECTION.md)。下一阶段 V1.1 将聚焦 **Any text / image → Books → WeRead**：支持从一整段文字或图片里提取多本书，并保留 `Douban + WeRead` 作为可选路径。

当前 V1 已支持：

- 📖 书名搜索
- 🔢 ISBN 精确搜索
- 📷 本地 OCR 识别书籍图片（RapidOCR / ONNX Runtime）
- 🤖 飞书机器人
- ❤️ 豆瓣「想读」确认写入与回读验证
- 📚 微信读书版本匹配与可用性检查
- 🔀 Douban Edition / WeRead Edition 分离，同一 Work 可对应不同平台版本
- 🔔 微信读书可用性定期检查
- 🍎 macOS LaunchAgent 后台自动启动

**不需要 OpenAI、Claude 或 Kimi API，也不会产生 LLM token 消耗。**

> This project is self-hosted. Each user should create and use their own Feishu app, Douban session and WeRead API key. Never share or commit real cookies or secrets.

## Requirements

- macOS / Linux
- Python 3.10+
- Git
- A Feishu app / bot if you want to use the chat interface
- Your own Douban Cookie for authenticated Want-to-Read actions
- Your own WeRead Agent API key for WeRead availability features

## Quick start

Clone the repository:

```bash
git clone https://github.com/LCubed101/douban-weread.git
cd douban-weread
```

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

RapidOCR is installed automatically through the project dependencies. OCR runs locally on your machine.

Create your local environment file:

```bash
cp .env.example .env
```

Fill in the values you actually use:

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
DOUBAN_COOKIE=
WEREAD_API_KEY=
DATABASE_URL=sqlite:///data/douban-weread.db
```

For step-by-step instructions on safely obtaining and storing the Douban Cookie and WeRead API key, see [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md).

Do **not** commit `.env` or paste real secrets into GitHub issues, screenshots or chat messages.

## Try the CLI first

Search by title:

```bash
douban-weread search "百年孤独"
```

Search by ISBN:

```bash
douban-weread search --isbn 9787544253994
```

The title search may return multiple editions so you can compare translator, publisher, publication date and ISBN.

## Run the Feishu bot

If this is your first time creating a Feishu bot, follow the step-by-step guide first: [docs/FEISHU_SETUP.md](docs/FEISHU_SETUP.md).

After configuring your own Feishu app credentials in `.env`:

```bash
douban-weread-feishu
```

The bot accepts book titles, ISBNs and images. Image OCR is performed locally with RapidOCR. When a cover is too ambiguous, the V1 behavior is conservative: it asks for a title, ISBN, Douban link, copyright page or barcode page instead of guessing an unrelated book.

## macOS: run automatically in the background

Install the LaunchAgent:

```bash
zsh scripts/install_launchagent.sh
```

It will start the bot immediately and launch it automatically when you log in to macOS.

Check whether it is running:

```bash
launchctl print gui/$(id -u)/com.lcubed.douban-weread.feishu | grep -E 'state =|pid =|runs =|last exit code'
```

A healthy result includes:

```text
state = running
pid = <PID>
```

Restart it manually if needed:

```bash
launchctl kickstart -k gui/$(id -u)/com.lcubed.douban-weread.feishu
```

Logs are written to:

```text
~/Library/Logs/douban-weread/bot.log
~/Library/Logs/douban-weread/bot.error.log
```

Uninstall the LaunchAgent:

```bash
zsh scripts/uninstall_launchagent.sh
```

## Douban authentication and Want-to-Read

Authenticated actions use a user-owned browser Cookie stored only in the local environment. The current implementation expects a complete `DOUBAN_COOKIE` containing at least `dbcl2` and `ck`.

Check authentication first:

```bash
douban-weread auth diagnose
douban-weread auth check
```

A state-changing CLI action requires explicit confirmation:

```bash
douban-weread wish --subject <DOUBAN_SUBJECT_ID> --confirm
```

Without `--confirm`, the command refuses to change state. After a write, the client reads the saved state back before reporting success.

See [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md) for safe credential setup and [docs/DOUBAN_AUTH.md](docs/DOUBAN_AUTH.md) for the provider's authentication details.

## How matching works

A book title is not a unique identity. The same Work can have different translators, publishers, publication dates, covers and ISBNs.

Edition matching prefers:

1. Exact ISBN match
2. Same title + author + translator
3. Same title + author + publisher
4. Same title + author + publication year
5. Same Work, different Edition available on WeRead

The core identity is the Work. Douban Edition and WeRead Edition are platform-specific and may legitimately differ. The router should preserve the user's chosen record while routing to an actually readable WeRead edition when appropriate.

## WeRead states

- `AVAILABLE_EXACT`
- `AVAILABLE_ALTERNATIVE`
- `COMING_SOON`
- `NOT_FOUND`

The current official WeRead interface used by this project supports read-side discovery and deep links. The project does **not** claim an official automatic shelf-add write flow where the upstream API does not expose one.

## Privacy and cost

This project is intended to be self-hosted.

- Feishu App ID / Secret stay in your local `.env`.
- Douban Cookie and WeRead API key stay on your own machine.
- Local OCR uses RapidOCR / ONNX Runtime and does not send image OCR work to an LLM.
- The current V1 does not call OpenAI, Anthropic/Claude or Kimi APIs.
- Keeping the bot running uses some local memory and network connections, but does not consume LLM tokens.

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for known failure modes and fixes.

Useful local checks:

```bash
ps aux | grep '[d]ouban-weread-feishu'
tail -50 ~/Library/Logs/douban-weread/bot.log
tail -50 ~/Library/Logs/douban-weread/bot.error.log
```

## Development

Run the full test suite:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Roadmap

See [ROADMAP.md](ROADMAP.md).

Current next milestone: **V1.1 Multi-book Text Inbox** — long text / image → extract multiple books → match WeRead, with Douban remaining optional.

## Acknowledgements

See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).

## License

MIT
