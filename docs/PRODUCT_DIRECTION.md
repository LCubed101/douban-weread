# Product Direction — Reading Inbox / Reading Router

## One-line definition

把任何地方偶然遇到的书，低摩擦地送进用户自己的阅读系统。

> Don't replace your system. Connect it.

This project is not trying to become a universal knowledge base or a new reading app. It should identify books from messy real-world inputs, confirm what they are, and route them into the tools each person already uses.

## Why this direction

The original personal workflow was:

```text
Social / screenshot / recommendation
        ↓
Identify the book
        ↓
Confirm the Douban edition
        ↓
Record it on Douban
        ↓
Find a readable WeRead edition
        ↓
Read
```

Feedback from real users broadened the input without changing the core job:

- Some people do not use Douban at all; they only want the book to reach WeRead.
- Some inputs are not book titles but long AI-generated or note-generated text containing multiple books.
- Some people want to paste arbitrary text or screenshots and have the system extract the books for them.
- Different people already have different reading and knowledge systems, so the router should not force a single destination.

The common problem is therefore not “sync Douban and WeRead.” It is:

> I encountered something that contains books. Help me identify the books and send them into my own reading workflow.

## Product model

The prototype should be organized around four stages:

```text
Capture
  ↓
Understand
  ↓
Confirm
  ↓
Route
```

### 1. Capture

Inputs may include:

- plain book title
- ISBN
- Douban link
- long pasted text
- AI-generated recommendation list
- screenshot
- book cover / copyright page / barcode page
- later: share sheet / shortcut / web input

Feishu is currently one interface for Capture. It is not the product boundary.

### 2. Understand

Convert raw input into books:

```text
Text / Image / URL
       ↓
Unified text
       ↓
Book Mention Extractor
       ↓
Book candidates / Works
```

OCR is only an adapter for image input. It should not be the center of the product.

For V1.1, extraction should be text-first and deterministic where possible:

- 《书名》
- 「书名」
- numbered lists
- bullet lists
- common recommendation patterns
- de-duplication

LLM extraction should be considered only after enough real samples show that deterministic extraction is insufficient.

### 3. Confirm

The system should fail closed when identity is uncertain.

The core identity is the Work, while Edition is platform-specific:

```text
             Work
              │
       ┌──────┴──────┐
       ↓             ↓
Douban Edition   WeRead Edition
   record            read
```

A Douban edition and a WeRead edition may legitimately differ while still representing the same Work.

Matching priority:

1. same ISBN
2. same edition by title / author / translator / publisher / date
3. same Work, different Edition
4. uncertain same Work → ask the user or fail closed

### 4. Route

Routing should be user-specific rather than hard-coded:

```text
Book detected
    ↓
Choose route
 ┌───────────────┬──────────────────┐
 ↓               ↓
WeRead only   Douban + WeRead
```

Future destinations may include other reading tools, but the prototype should stay focused on books.

## Current product boundary

### In scope

- Books only
- Text / ISBN / Douban URL / image input
- Identify one or more books
- Work / Edition confirmation
- Douban Want-to-Read route
- WeRead readable-edition route
- Preserve existing reading history
- Self-hosted, user-owned credentials

### Not in scope yet

- Generic Knowledge Inbox
- Notes / highlights / reading-progress management
- Knowledge graph
- Vector database / embeddings as a product requirement
- Automatic summarization of books
- Movies / TV / podcasts / articles as first-class routed objects
- Replacing flomo, Obsidian, Notion, Douban, WeRead, etc.

## Relationship to a Personal Context System

Reading Inbox is a vertical prototype of a broader idea:

```text
Personal Context System
        │
        ├── Reading Inbox → Books
        ├── Idea Inbox    → notes / thoughts
        ├── Project Context → repos / docs
        └── other object routers later
```

The broader principle is:

> Do not require all information to live in one place. Preserve enough identity and context so it can reach the right existing system and be recalled later.

The project should not expand into that broader system until the Reading Inbox has been validated through real use.

## Product principles

- Don't replace the user's existing system. Connect it.
- Books are the current vertical; resist premature generic expansion.
- Work is the core identity; Edition is platform-specific.
- Text first; OCR is fallback.
- Prefer deterministic extraction before adding LLM cost and complexity.
- Preserve user judgment for meaningful decisions.
- Fail closed when identity is uncertain.
- Keep routing optional: Douban is one route, not a mandatory step.
- Every added feature should be justified by a real captured use case.

## V1.1 target

The next prototype milestone is:

> **Any text / image → Books → WeRead**, while retaining **Douban + WeRead** as an optional personal route.

Acceptance criteria:

1. Feishu accepts a long block of text.
2. The system extracts multiple explicit book mentions from that text.
3. Image OCR feeds into the same extractor rather than a separate book-search path.
4. Duplicate mentions are collapsed.
5. Every extracted book is matched against WeRead.
6. The user gets a readable WeRead deep link where available.
7. Douban remains optional rather than mandatory.
8. No LLM API is required for the first implementation.

## Validation before expanding

Before adding generic knowledge/context features, collect real examples from actual use:

- 5–10 flomo / AI Insight outputs
- 5–10 social-media or chat snippets containing books
- 5–10 screenshots where OCR is genuinely necessary

For each sample, record:

- input type
- whether text was directly copyable
- how book titles were formatted
- number of books mentioned
- extraction errors
- WeRead matching errors
- whether the user actually continued to read / save the book

The next architecture decisions should come from these samples rather than from hypothetical feature breadth.
