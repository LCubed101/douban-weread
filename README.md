# Douban × WeRead

A self-hosted **Recommendation Router** prototype.

> 把别人推荐给我的东西，低摩擦地送进我真正使用的平台。
>
> Don't replace your system. Connect it.

The project started as a Reading Inbox / Reading Router for books and is now validating the broader **Capture → Identify → Confirm → Route** model across cultural recommendations.

Current C-end target user:

> 已经在使用豆瓣 / 微信读书 / 小宇宙等内容平台，经常从微信、社交媒体和朋友聊天里收到书影音推荐，但不想再维护一个新的收藏工具的人。

Feishu is currently the main Capture adapter. It is not the product boundary or the final knowledge store. The destination apps keep owning the long-term state.

Product direction, ICP, boundaries and validation metrics: [docs/PRODUCT_DIRECTION.md](docs/PRODUCT_DIRECTION.md).

Current usable capabilities include:

- 📖 Book title / ISBN search
- 📷 Local OCR for screenshots and book images (RapidOCR / ONNX Runtime)
- 📚 Multi-book extraction from long text / screenshots
- ❤️ Douban Want-to-Read confirmation + persisted-state verification
- 📚 WeRead edition matching and availability checks
- 🔀 Douban Edition / WeRead Edition separation for the same Work
- 🔔 WeRead Waiting List / availability re-checking
- 🎬 Film / TV / Documentary → Douban Want-to-Watch
- 🔘 Same-title Book / Movie disambiguation with direct buttons
- 📺 TV season-family recognition and season choice
- 🧩 Safe mixed Book + Movie routing
- 🤖 Feishu Bot as the current Capture interface
- 🍎 macOS LaunchAgent background startup

Podcast Episode Router → Xiaoyuzhou is **still under exploration / validation and is not yet a shipped C-end feature**.

**No OpenAI, Claude or Kimi API is required by the current production path, so normal routing does not incur LLM token usage.**

> This project is self-hosted. Each user should create and use their own Feishu app and WeRead API key. Douban credentials are only needed when the user chooses the Douban recording path. Never share or commit real cookies or secrets.

## Product model

```text
Capture
  ↓
Understand / Identify
  ↓
Confirm only when needed
  ↓
Route
```

Current destination model:

```text
📚 Book → 豆瓣想读 → 微信读书可读链接
🎬 Film / TV / Documentary → 豆瓣想看
🎧 Podcast episode → 小宇宙（探索中，未正式上线）
```

Pure thoughts / quotations / ideas stay in the user's existing note tool such as flomo. This project should not become a duplicate knowledge base.

## Requirements

- macOS / Linux
- Python 3.10+
- Git
- A Feishu app / bot if you want to use the chat interface
- Your own WeRead Agent API key for WeRead availability features
- Your own Douban Cookie **only if** you want authenticated Douban Want-to-Read / Want-to-Watch actions

## Quick start

Clone the repository:

```bash
git clone https://github.com/LCubed101/douban-weread.git
cd douban-weread
git checkout agent/weread-shelf-baseline
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

For a WeRead-only friend test, fill only:

```env
FEISHU_APP_ID=
FEISHU_APP_SECRET=
WEREAD_API_KEY=
DATABASE_URL=sqlite:///data/douban-weread.db
DOUBAN_COOKIE=
```

Leave `DOUBAN_COOKIE` blank when you do not use Douban.

For step-by-step instructions, see [docs/FEISHU_SETUP.md](docs/FEISHU_SETUP.md), [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md), or the shorter [WeRead-only friend setup](docs/FRIEND_TEST_WEREAD_ONLY.md).

Do **not** commit `.env` or paste real secrets into GitHub issues, screenshots or chat messages.

## Try WeRead first

Load the environment:

```bash
set -a
source .env
set +a
```

Test the official read-only WeRead API:

```bash
douban-weread weread search "专注" --limit 5
```

If this returns candidates, the WeRead key is working.

## Run the Feishu bot

If this is your first time creating a Feishu bot, follow the step-by-step guide first: [docs/FEISHU_SETUP.md](docs/FEISHU_SETUP.md).

After configuring your own Feishu app credentials in `.env`:

```bash
set -a
source .env
set +a

douban-weread-feishu
```

The preferred UX is intentionally lightweight:

```text
看到 → 识别 → 必要时选一次 → 完成
```

When identity is uncertain, the router should ask rather than silently guessing.

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

## Douban authentication (optional)

Authenticated Douban actions use a user-owned browser Cookie stored only in the local environment.

If you choose to use Douban, the current implementation expects a complete `DOUBAN_COOKIE` containing at least `dbcl2` and `ck`.

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

See [docs/AUTH_SETUP.md](docs/AUTH_SETUP.md) for safe credential setup and [docs/DOUBAN_AUTH.md](docs/DOUBAN_AUTH.md) for provider details.

## How book matching works

A book title is not a unique identity. The same Work can have different translators, publishers, publication dates, covers and ISBNs.

Edition matching prefers:

1. Exact ISBN match
2. Same title + author + translator
3. Same title + author + publisher
4. Same title + author + publication year
5. Same Work, different Edition available on WeRead

For title-only recommendation lists, a separate conservative WeRead-first resolver can route exact normalized title matches directly, while fuzzy titles remain fail-closed.

## WeRead states

- `AVAILABLE_EXACT`
- `AVAILABLE_ALTERNATIVE`
- `UNAVAILABLE`
- `NOT_FOUND`

The current official WeRead interface used by this project supports read-side discovery and deep links. The project does **not** claim an official automatic shelf-add write flow where the upstream API does not expose one.

## Privacy and cost

This project is intended to be self-hosted.

- Feishu App ID / Secret stay in your local `.env`.
- WeRead API key stays on your own machine.
- Douban Cookie is optional and only needed for authenticated Douban routes.
- Local OCR uses RapidOCR / ONNX Runtime and does not send image OCR work to an LLM.
- The current production path does not require OpenAI, Anthropic/Claude or Kimi APIs.
- Keeping the bot running uses some local memory and network connections, but does not consume LLM tokens.
- Ordinary future C-end users should not be required to capture private app tokens or install HTTPS debugging proxies.

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

The current product priority is not “add every content type.” It is validating that **Capture → Route becomes a repeated user habit** with a narrow C-end cohort.

## Acknowledgements

See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).

## License

MIT
