# User Feedback Log

This document keeps external feedback separate from product decisions. The goal is to preserve what users actually asked for before translating it into roadmap items.

## 2026-08-25 — Reading Inbox / Reading Router feedback

### 1. Douban + WeRead is useful when Douban is the personal reading record

**Feedback**

A user asked: if the book title is already known, why not search WeRead directly and add it to the shelf?

**Underlying need**

For some users, Douban is not just a discovery source. It is the long-term reading record, while WeRead is the place where reading happens.

**Implication**

- Do not assume everyone wants a WeRead-only flow.
- Keep routing preferences user-specific.
- Douban and WeRead should remain separate output adapters rather than one hard-coded chain.

---

### 2. flomo AI Insight → extract books → WeRead

**Feedback**

A user receives book recommendations from flomo AI Insight as a large block of text and wants the system to extract only the book names and match them to WeRead.

They do not necessarily need Douban in this flow.

**Related comments**

- Screenshot input would be convenient when text is not easy to copy.
- Direct flomo → WeRead might be more convenient, but this is currently a relatively low-frequency problem.
- Feishu is an acceptable temporary input interface for users already used to Feishu.

**Implication**

- Support multi-book extraction from one input.
- Make the core flow provider-neutral: raw content → books → route.
- Prefer copyable text before OCR when possible.
- Do not make direct flomo integration a prerequisite for V1.1.

---

### 3. Any information should be able to reveal book mentions

**Feedback**

A user asked whether the system could extract book names from arbitrary information, rather than requiring the user to first send a clean book title.

Possible sources include:

- articles
- chats
- social posts
- AI responses
- reading lists
- screenshots

**Implication**

The product should evolve from a `Book Inbox` that assumes the title is already known toward a `Reading Inbox` that can identify books inside surrounding context.

This directly supports the V1.1 `Book Mention Extractor` work.

---

### 4. Reading helper / browser plugin

**Feedback**

Someone in the group suggested making a “reading helper” plugin.

**Possible interaction**

While reading a webpage, a user could select text or open the extension and see the books mentioned in the current context, then route them to WeRead / Douban.

**Implication**

- Browser Extension is a natural future Capture Adapter.
- It should reuse the same Book Mention Extractor / Work resolver / Router core.
- Do not build the extension before validating the underlying multi-book extraction behavior.

---

### 5. Knowledge-base direction / electronic reading capture

**Source feedback**

A user said the idea is useful and connected it to a previous AI-bookmark concept. They also expressed a stronger desire for a way to directly collect electronic reading material into a knowledge base, potentially even through dedicated hardware.

A related reply suggested that a “reading helper plugin” could be feasible.

**Implication**

This is a signal toward a broader personal Knowledge / Context system, but it is not yet the current product scope.

For now:

- preserve this as future-direction evidence;
- continue validating Books as the first vertical;
- avoid expanding immediately into a generic Knowledge Inbox;
- treat “collecting reading material into a knowledge base” as a separate future workflow from “routing a discovered book into a reading system.”

---

### 6. Interaction feedback: card actions need immediate visual acknowledgement

**Feedback**

After tapping a Feishu card button, users could not tell whether the click had registered and might tap repeatedly.

**Expected behavior**

- Button state should visibly change immediately.
- The original action buttons should disappear or become inactive.
- The card should show a clear acknowledged / processing state.

**Status**

Implemented in the Feishu interaction layer: card actions now return an updated acknowledged card state.

---

### 7. Interaction feedback: WeRead links should be buttons/cards, not raw URLs

**Feedback**

A plain `可读链接：https://...` line feels unfinished and is harder to use than a card action.

**Expected behavior**

Show a clear `打开微信读书` action in a Feishu card.

**Status**

Implemented in the Feishu UI layer for outbound WeRead readable links.

---

### 8. Conversation control: allow the user to explicitly end the current book-selection flow

**Feedback**

When the bot is holding a multi-edition selection context, users need an obvious way to stop that flow and start searching for a different book.

**Expected behavior**

Provide a visible `结束本次找书` action that clears the current candidate context.

**Status**

Implemented in the Feishu selection flow.

---

### 9. Recommendations are not limited to books: documentary / creator / cross-platform subscription routing

**Feedback**

Users may be recommended things other than books, including documentaries and creators. A creator may exist on different platforms such as YouTube and Bilibili.

The desired experience is to avoid manually copying a creator name, opening each platform, searching again, checking identity, and then subscribing.

**Expected behavior**

From one piece of recommendation context, the system could identify the recommended entity and present direct platform actions, for example:

```text
识别到：某个创作者

[打开 YouTube 频道]
[打开 Bilibili 主页]
```

For documentaries or videos, the same pattern could route to the relevant watch / save destination.

**Implication**

This is a strong signal that the long-term core may generalize from `Book Mention Extractor` toward:

```text
Mention Extractor
      ↓
Entity Resolver
      ↓
Router
```

Possible entity types include:

- Book
- Documentary / Video
- Creator
- Podcast
- Article / Repo

However, this should not expand the current V1.1 scope yet. Books remain the first vertical because the existing Douban / WeRead flow already gives a complete route for validating the “extract → resolve → route” pattern.

Automatic subscription should not be assumed. Where platforms do not expose a suitable official write API / OAuth path, the first useful step is a direct, verified platform button rather than hidden automation.

---

## Signals vs. current scope

### Repeated signals

The feedback so far consistently points toward:

```text
content / screenshot / webpage / AI output
                ↓
        identify useful mentions
                ↓
        resolve the real entity
                ↓
        route to user's system
```

For the current book vertical:

```text
content / screenshot / webpage / AI output
                ↓
        identify book mentions
                ↓
             Books / Work
                ↓
        route to user's system
          ↙              ↘
      WeRead            Douban
```

### Current scope

The current prototype remains a **Reading Inbox / Reading Router for books**.

It should not yet become:

- a generic Knowledge Inbox
- a complete second brain
- a universal note-taking system
- a movie / TV router
- a universal creator subscription manager
- a hardware product

Those ideas stay in the feedback log until repeated real use justifies expansion.

## Product principle emerging from feedback

> Do not replace the user's reading or knowledge system. Help discoveries reach the system they already use.
