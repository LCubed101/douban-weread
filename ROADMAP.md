# Roadmap

The project is converging from a narrow Douban × WeRead sync workflow into a **Reading Inbox / Reading Router**:

> 把任何地方偶然遇到的书，低摩擦地送进用户自己的阅读系统。

See [docs/PRODUCT_DIRECTION.md](docs/PRODUCT_DIRECTION.md) for the product definition and boundaries.

## V1 — Single-book Reading Router

Status: usable prototype.

Current focus:

- [x] Search Douban by title
- [x] Search Douban by ISBN
- [x] Accept Feishu text input
- [x] Accept book images through local OCR
- [x] Confirm exact Douban Edition before mutation
- [x] Protect existing `READ` / `READING` history from downgrade
- [x] Write Douban `WISH` only after explicit confirmation
- [x] Verify Douban state after writes
- [x] Search and align WeRead editions
- [x] Distinguish exact Edition vs same-Work alternative Edition
- [x] Show WeRead availability before choosing among multiple Douban editions
- [x] Preserve candidate context when the user selects “不是这本”
- [x] Support explicit end-of-search / reset flow in Feishu
- [x] Periodically recheck unavailable WeRead matches
- [x] Run as a macOS LaunchAgent

V1 validates the core loop:

```text
Capture → Identify → Confirm → Route
```

## V1.1 — Multi-book Text Inbox

**Next implementation milestone.**

Goal:

> Any text / image → Books → WeRead

while keeping **Douban + WeRead** as an optional route for users who want Douban as their reading record.

### A. Book Mention Extractor

- [ ] Add a provider-neutral `BookMention` / extraction layer
- [ ] Extract explicit `《书名》` patterns
- [ ] Extract `「书名」` patterns where confidence is high
- [ ] Extract numbered and bullet-list book recommendations
- [ ] Handle common prefixes such as “推荐：” / “书单：”
- [ ] De-duplicate repeated titles
- [ ] Keep single plain-title input working exactly as it does today
- [ ] Fail closed rather than inventing titles from ambiguous prose

### B. Long text in Feishu

- [ ] Accept a pasted long block of text
- [ ] Extract multiple books from one message
- [ ] Show the extracted list before routing when necessary
- [ ] Batch-resolve books without treating the whole paragraph as one Douban title
- [ ] Keep the interaction lightweight enough for copied AI / flomo output

### C. Unified image path

- [ ] Route image OCR output into the same Book Mention Extractor
- [ ] Remove separate assumptions that an image must represent exactly one title
- [ ] Keep OCR conservative when the text is noisy
- [ ] Benchmark OCR only against real collected samples before changing engines

### D. WeRead-first routing

- [ ] Allow a WeRead-only path without requiring `DOUBAN_COOKIE`
- [ ] Batch-match each extracted Work against WeRead
- [ ] Return readable deep links for matches
- [ ] Clearly distinguish exact Edition vs same-Work alternative Edition
- [ ] Keep unsupported automatic shelf-add out of scope until an official write API exists

### E. Optional Douban route

- [ ] Keep Douban as an optional route instead of a mandatory pipeline stage
- [ ] Allow `Douban + WeRead` for users who use Douban as the reading record
- [ ] Preserve Work / Edition separation across both platforms

### V1.1 acceptance criteria

- [ ] Feishu accepts long text containing multiple books
- [ ] Multiple explicit book names are extracted
- [ ] Images feed into the same extraction pipeline
- [ ] Duplicate book mentions are collapsed
- [ ] Every extracted book can be checked against WeRead
- [ ] WeRead deep links are returned where available
- [ ] Douban is optional
- [ ] No OpenAI / Claude / Kimi API is required

## Validation track — Real inputs before more architecture

Before introducing LLM extraction or broader Knowledge Inbox features:

- [ ] Collect 5–10 real flomo / AI Insight outputs
- [ ] Collect 5–10 social / chat / article snippets containing books
- [ ] Collect 5–10 screenshots where OCR is genuinely necessary
- [ ] Record title formatting patterns
- [ ] Record extraction failures
- [ ] Record WeRead matching failures
- [ ] Record whether the routed book was actually saved / opened / read

Decision rule:

> Add complexity only when real samples demonstrate a repeated failure mode.

## V1.2 — More capture interfaces

Only after V1.1 is stable:

- [ ] macOS Shortcut / Share Sheet
- [ ] Lightweight web input
- [ ] CLI multi-book paste input
- [ ] Pluggable capture interfaces

Feishu remains an adapter, not the product boundary.

## Later — Personal Context Router exploration

This is a direction, **not the current product scope**.

Potential model:

```text
Personal Context System
        │
        ├── Reading Inbox → Books
        ├── Idea Inbox → notes / thoughts
        ├── Project Context → repos / docs
        └── other routers later
```

Do not expand here until the books vertical has enough real usage evidence.

Explicitly deferred:

- generic Knowledge Inbox
- vector database / embeddings as a requirement
- knowledge graph
- universal note storage
- movie / TV routing
- article / podcast routing
- automatic book summarization
- replacing flomo / Obsidian / Notion / Douban / WeRead

## Engineering principles

- Self-hosted first
- Don't replace the user's existing system; connect it
- Work and Edition are separate entities
- Reading state belongs to a specific platform + Edition
- Known `READ` / `READING` state must not be silently downgraded to `WISH`
- No title-only destructive matching
- Preserve original discovery context
- Text first; OCR is fallback
- Prefer deterministic extraction before adding LLM cost / complexity
- Prefer explicit user confirmation over silent substitution
- Fail closed when identity is uncertain
- Clearly label unofficial APIs / reverse-engineered interfaces
- Credit upstream projects and comply with their licenses
