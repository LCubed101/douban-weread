# Douban × WeRead

让你在飞书里发来的书名、ISBN 或书籍图片，经过识别后匹配豆瓣版本，并继续检查微信读书中的可读版本。

当前 V1 已支持：

- 📖 书名搜索
- 🔢 ISBN 精确搜索
- 📷 本地 OCR 识别书籍图片（RapidOCR / ONNX Runtime）
- 🤖 飞书机器人
- ❤️ 豆瓣「想读」确认写入与回读验证
- 📚 微信读书版本匹配与可用性检查
- 🔔 微信读书可用性定期检查
- 🍎 macOS LaunchAgent 后台自动启动

**不需要 OpenAI、Claude 或 Kimi API，也不会产生 LLM token 消耗。**

> This project is self-hosted. Each user should create and use their own Feishu app, Douban session and WeRead session. Never share or commit real cookies or secrets.

## Requirements

- macOS / Linux
- Python 3.10+
- Git
- A Feishu app / bot if you want to use the chat interface
- Your own Douban Cookie for authenticated Want-to-Read actions
- Your own WeRead Cookie for WeRead availability / shelf features

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
WEREAD_COOKIE=
DATABASE_URL=sqlite:///data/douban-weread.db
```

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
douban-weread auth check
```

A state-changing CLI action requires explicit confirmation:

```bash
douban-weread wish --subject <DOUBAN_SUBJECT_ID> --confirm
```

Without `--confirm`, the command refuses to change state. After a write, the client reads the saved state back before reporting success.

The authenticated Book interest route is an unofficial/internal interface and may change. See [docs/DOUBAN_AUTH.md](docs/DOUBAN_AUTH.md).

## How matching works

A book title is not a unique identity. The same work can have different translators, publishers, publication dates, covers and ISBNs.

Edition matching prefers:

1. Exact ISBN match
2. Same title + author + translator
3. Same title + author + publisher
4. Same title + author + publication year
5. Same work, different edition available on WeRead

The project tries to preserve the edition you discovered while aligning the practical reading target to an edition that is actually readable on WeRead.

## WeRead states

- `AVAILABLE_EXACT`
- `AVAILABLE_ALTERNATIVE`
- `COMING_SOON`
- `NOT_FOUND`

## Privacy and cost

This project is intended to be self-hosted.

- Feishu App ID / Secret stay in your local `.env`.
- Douban and WeRead cookies stay on your own machine.
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

## Acknowledgements

See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).

## License

MIT
