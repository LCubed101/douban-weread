# Product Direction — Recommendation Router

## One-line definition

把别人推荐给我的东西，低摩擦地送进我真正使用的平台。

> Don't replace your system. Connect it.

The product is not trying to become another universal knowledge base, reading app, media tracker, or note-taking system. It should accept messy real-world recommendations, identify the object, ask only when identity is uncertain, and route it into the destination the user already trusts.

## Core user job

The common problem is not a lack of recommendations. It is that recommendations arrive everywhere and are easy to lose:

```text
Social media / group chat / friend / screenshot / article
                         ↓
                    recommendation
                         ↓
                "I want this later"
                         ↓
        screenshot / favorite / send to self / forget
```

The product job is:

> I encountered something I may want later. Help me identify it and send it to the right place without asking me to maintain another collection system.

## First C-end ICP

**Ideal Customer Profile (ICP):**

> 已经在使用豆瓣 / 微信读书 / 小宇宙等内容平台，经常从微信、社交媒体和朋友聊天里收到书影音推荐，但不想再维护一个新的收藏工具的人。

Typical traits:

- regularly receives book / film / TV / podcast recommendations
- already has trusted destination apps
- recommendations are scattered across screenshots, chats, social feeds and saved messages
- the pain is fragmentation and forgotten intent, not insufficient content supply
- values low-friction capture more than another dashboard or recommendation feed

The first product validation target is intentionally narrow. Do not optimize for “everyone who likes content” yet.

## Product model

The product should be organized around four stages:

```text
Capture
  ↓
Understand / Identify
  ↓
Confirm only when needed
  ↓
Route
```

### 1. Capture

Inputs may include:

- plain text
- screenshot / image
- copied recommendation list
- link
- forwarded chat / social content
- later: Share Sheet, browser extension, shortcut, lightweight web input

Feishu Bot is currently a Capture adapter. It is not the product boundary or the final knowledge store.

### 2. Understand / Identify

Convert messy input into explicit objects:

```text
Text / Image / URL
       ↓
Unified input
       ↓
Mention / entity extraction
       ↓
Book / Film / TV / Podcast candidates
```

Prefer deterministic parsing and platform metadata where possible. OCR is an adapter for image input, not the center of the product.

### 3. Confirm

The product should fail closed when identity is uncertain.

Principle:

> Low friction does not mean zero confirmation.

Desired interaction:

```text
看到
 ↓
识别
 ↓
必要时选一次
 ↓
完成
```

A wrong automatic route damages trust more than one lightweight confirmation. Ambiguous editions, same-title books/films, TV seasons, and similar entities should use direct choices rather than guessing.

### 4. Route

Current / intended destination model:

```text
📚 Book
   → 豆瓣想读（record）
   → 微信读书可读链接（read）

🎬 Film / TV / Documentary
   → 豆瓣想看

🎧 Podcast episode
   → 小宇宙 episode URL
   → currently exploration / validation, not yet a shipped user feature
```

The destination owns the long-term state. The router should not create a duplicate library unless a future use case proves it is necessary.

## Knowledge / note boundary

Pure thoughts, quotations and ideas are not the same product object as books, films or podcast episodes.

```text
有明确对象的推荐
→ Recommendation Router

纯观点 / 摘抄 / 灵感
→ flomo or the user's existing note tool
```

Feishu should not become a second copy of flomo. The product should connect existing systems rather than duplicate them.

## What the product competes with

The practical alternatives are not primarily Douban, WeRead or Xiaoyuzhou. They are:

- screenshot and forget
- WeChat Favorites
- send to self
- browser bookmarks
- Notes
- flomo / other capture tools
- “I will remember this later”

The product therefore wins by reducing cognitive and operational friction:

> 比“先截图以后再说”更省脑子。

## Current product boundary

### Shipped / usable direction

- Books from text / ISBN / screenshot
- Multiple books from long text / images
- Douban Want-to-Read route
- WeRead availability / readable-edition route
- Film / TV / Documentary → Douban Want-to-Watch
- Same-title Book / Movie disambiguation
- TV season-family disambiguation
- Mixed Book + Movie routing for safe cases
- Feishu as the current Capture adapter

### Exploration, not yet shipped as a C-end feature

- Podcast Episode Router → Xiaoyuzhou
- Public Xiaoyuzhou episode matching without user credentials
- Share Sheet / browser extension / additional Capture adapters

### Explicitly not the goal

- universal knowledge base
- replacing flomo / Obsidian / Notion
- replacing Douban / WeRead / Xiaoyuzhou
- AI recommendation feed
- generic “save everything” app
- knowledge graph as a product requirement
- asking ordinary users to capture private app tokens or install HTTPS debugging proxies

## C-end validation

The next milestone is not “support more entity types.” It is proving that **Capture → Route becomes a repeated habit**.

### North Star

**Weekly Routed Items per Active User**

Count items that successfully reach the intended destination, not merely messages received by the bot.

### Supporting metrics

**Activation**

> A new user successfully routes one object within the first session.

**D7 Repeat Capture**

> After the first successful route, does the user voluntarily come back and capture another recommendation within 7 days?

**Wrong Route Rate**

> Incorrect automatic routing should remain as close to zero as possible. Prefer `AMBIGUOUS` / confirmation over a confident wrong route.

### First validation cohort

Before expanding further:

- recruit 10–20 target users
- observe 1–2 weeks of real use
- collect 100–300 real Capture events
- record source, object type, success / confirmation / failure, and whether users return without prompting

The strongest early signal is not MAU. It is:

> A user chooses to send a second recommendation to the product without being reminded.

## Product principles

- Don't replace the user's existing system. Connect it.
- The router is an intake / routing layer, not the final destination.
- Recommendations are abundant; the problem is attention and fragmentation.
- Do not add an AI recommendation feed before routing behavior is validated.
- Prefer one lightweight confirmation over a wrong automatic route.
- Preserve user judgment for meaningful decisions.
- Fail closed when identity is uncertain.
- Keep destinations user-specific rather than hard-coded as a single workflow.
- Ordinary C-end users should not need developer credentials, tokens, Charles, or manual API setup.
- Every added entity type or Capture adapter should be justified by real user behavior.

## Product thesis

> You already have enough recommendations. We help them reach the right place.

Or, in Chinese:

> 你已经不缺推荐了。我们只负责把它们送到对的地方。
