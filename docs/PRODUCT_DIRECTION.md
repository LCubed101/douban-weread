# Product Direction — Reading Router

## One-line definition

把别人推荐给我的书，低摩擦地送进我真正使用的阅读系统。

> Don't replace your system. Connect it.

The main product is intentionally **Book only**. It is not trying to become a universal recommendation router, media tracker, knowledge base, or note-taking app.

## Core user job

Books are often discovered in fragmented places:

```text
Social media / group chat / friend / screenshot / article
                         ↓
                     a book
                         ↓
                "I want this later"
                         ↓
        screenshot / favorite / send to self / forget
```

The product job is:

> I encountered a book I may want to read. Help me identify it, record the intent, and tell me whether I can read it in the tool I already use.

## First C-end ICP

**Ideal Customer Profile (ICP):**

> 已经在使用豆瓣和 / 或微信读书，经常从微信、社交媒体、群聊和朋友聊天里收到图书推荐，但不想反复手动搜索、也不想维护一个新的收藏工具的人。

Typical traits:

- regularly receives book recommendations
- already uses Douban, WeRead, or both
- recommendations are scattered across screenshots, chats and social feeds
- the pain is fragmentation and repeated searching, not insufficient recommendations
- wants low-friction capture without another dashboard

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

### 1. Capture

Inputs may include plain text, ISBN, screenshot / image, copied book lists, links and forwarded social content. Feishu Bot is currently a Capture adapter, not the product boundary or the final knowledge store.

### 2. Understand / Identify

```text
Text / Image / URL
       ↓
Unified input
       ↓
Book Mention Extraction
       ↓
Book / Work candidates
```

Prefer deterministic parsing and platform metadata where possible. OCR is an adapter for image input, not the center of the product.

### 3. Confirm

The product should fail closed when identity is uncertain.

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

A wrong automatic route damages trust more than one lightweight confirmation.

### 4. Route

Mainline destination model:

```text
📚 Book
   → 豆瓣想读（record）
   → 微信读书可读链接（read）
```

The product does not replace either destination.

A useful semantic distinction is:

> 豆瓣负责「我想读什么」，微信读书负责「我现在能不能读」。

## Why Film / TV are not in the main product

For the primary workflow, Film / TV recommendations involve a different behavior: the user often wants to open Douban, inspect ratings / reviews, and then decide whether to watch. That judgment is meaningful and should not be automatically skipped.

The previous Movie / TV implementation is preserved separately in:

```text
experiment/movie-router
```

That branch can continue serving users who explicitly want `Film / TV / Documentary → Douban Want-to-Watch`, without broadening the Book-only main product.

## Knowledge / note boundary

Pure thoughts, quotations and ideas should continue to live in the user's existing note tool, such as flomo.

```text
图书推荐
→ Reading Router

观点 / 摘抄 / 灵感
→ flomo or the user's existing note tool
```

Feishu should not become a second copy of flomo.

## Current main product boundary

### In scope

- Books from text / ISBN / screenshot
- Multiple books from long text / images
- Work / Edition confirmation
- Douban Want-to-Read route
- WeRead availability / readable-edition route
- WeRead Waiting List / re-checking
- Feishu as the current Capture adapter
- Future low-friction Capture interfaces such as Share Sheet / browser extension

### Separate experiment

- Movie / TV / Documentary Router → `experiment/movie-router`

### Not part of the main product now

- Film / TV / Documentary routing
- Podcast routing
- universal Recommendation Router
- universal knowledge base
- replacing flomo / Obsidian / Notion
- AI recommendation feed
- generic “save everything” app
- knowledge graph as a product requirement

## C-end validation

The next milestone is not “support more entity types.” It is proving that **Book Capture → Route becomes a repeated habit**.

### North Star

**Weekly Routed Books per Active User**

Count books that successfully reach the intended reading workflow, not merely messages received by the bot.

### Supporting metrics

**Activation** — a new user successfully routes one book in the first session.

**D7 Repeat Capture** — after the first successful route, does the user voluntarily send another book within 7 days?

**Wrong Route Rate** — incorrect automatic routing should remain as close to zero as possible.

### First validation cohort

- recruit 10–20 target users
- observe 1–2 weeks of real use
- collect 100–300 real Book Capture events
- record source, success / confirmation / failure, and whether users return without prompting

The strongest early signal is:

> A user chooses to send a second book to the product without being reminded.

## Product principles

- Don't replace the user's existing system. Connect it.
- Book only for the main product until repeat behavior is validated.
- Automate transport; preserve meaningful user judgment.
- Prefer one lightweight confirmation over a wrong automatic route.
- Fail closed when identity is uncertain.
- Recommendations are abundant; the problem is attention and fragmentation.
- Do not add an AI recommendation feed before routing behavior is validated.
- Every added Capture adapter should be justified by real user behavior.

## Product thesis

> You already have enough book recommendations. We help them reach the right place.

Or, in Chinese:

> 你已经不缺书单了。我们只负责把想读的书送回你的阅读系统。
