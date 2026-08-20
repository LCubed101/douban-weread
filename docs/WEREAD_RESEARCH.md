# WeRead search / availability research

Status: **technical reconnaissance complete; official-provider implementation and read-only CLI landed; 123 local tests passing; first live search passed; /book/info live validation pending**.

Date: 2026-08-20

## Decision

Use the official Tencent WeChatReading Agent API as the first WeRead provider instead of reverse-engineering the consumer Web reader search flow.

Official repository:

- https://github.com/Tencent/WeChatReading
- search contract: https://github.com/Tencent/WeChatReading/blob/main/skills/search.md
- book metadata contract: https://github.com/Tencent/WeChatReading/blob/main/skills/book.md

The official skill currently documents version `1.0.4` and uses:

```text
POST https://i.weread.qq.com/api/agent/gateway
Authorization: Bearer $WEREAD_API_KEY
Content-Type: application/json
```

Every request body includes `skill_version` plus `api_name` and business parameters at the top level.

API keys are obtained from:

```text
https://weread.qq.com/r/weread-skills
```

The key is user-bound. It must remain local and must never be committed or pasted into logs/docs.

## Search endpoint

For ordinary e-book lookup, the official contract is:

```json
{
  "api_name": "/store/search",
  "keyword": "三体",
  "scope": 10,
  "count": 10,
  "skill_version": "1.0.4"
}
```

Important documented fields include:

```text
sid
hasMore
results[].title
results[].scope
results[].books[].searchIdx
results[].books[].bookInfo.bookId
results[].books[].bookInfo.deepLink
results[].books[].bookInfo.title
results[].books[].bookInfo.author
results[].books[].bookInfo.cover
results[].books[].bookInfo.intro
results[].books[].bookInfo.publisher
results[].books[].bookInfo.category
results[].books[].bookInfo.payType
results[].books[].bookInfo.price
results[].books[].bookInfo.soldout
results[].books[].readingCount
results[].books[].newRating
```

For this project, `scope=10` should be explicit because the product is matching ordinary e-books, not doing a generic multi-tab WeRead search.

The official documentation warns that the response grouping field `results[].scope` may be `17` even when the request used `scope=10`. Therefore the provider must not filter e-book groups by requiring `results[].scope == 10`.

Search results are paginated fragments, not an exhaustive catalog proof. `hasMore` and the final `searchIdx` are available for pagination.

## Book metadata endpoint

After selecting a search candidate, call:

```json
{
  "api_name": "/book/info",
  "bookId": "<weread book id>",
  "skill_version": "1.0.4"
}
```

The official contract documents these matching-relevant fields:

```text
bookId
deepLink
title
author
translator
cover
publisher
publishTime
isbn
```

This is enough to normalize a WeRead candidate into the project's existing `Edition` model:

```text
bookId       -> Edition.weread_id
title        -> Edition.title
author       -> Edition.authors
translator   -> Edition.translators
publisher    -> Edition.publisher
publishTime  -> Edition.publish_date
isbn         -> Edition.isbn
cover        -> Edition.cover_url
raw fields   -> Edition.source_metadata
```

`author` and `translator` are documented as strings. Provider normalization should be conservative and preserve raw values in `source_metadata`; parsing must not invent people when the delimiter is ambiguous.

## Availability semantics

The current project model already contains:

```text
AVAILABLE_EXACT
AVAILABLE_ALTERNATIVE
COMING_SOON
NOT_FOUND
```

The official APIs give enough evidence for the first, second, and negative-search paths, but **do not currently document a reliable `COMING_SOON` signal**.

Recommended v0.2 semantics:

```text
search candidate exists
+ soldout != 1
+ resolver says exact Edition
=> AVAILABLE_EXACT

search candidate exists
+ soldout != 1
+ resolver says same Work / alternative Edition
=> AVAILABLE_ALTERNATIVE

search exhausted within the configured search policy
+ no same-Work candidate
=> NOT_FOUND

soldout == 1
=> unavailable candidate; do not treat as readable

COMING_SOON
=> do not infer yet; leave unsupported until an official field or live evidence provides a stable signal
```

A search hit alone is not sufficient to declare `AVAILABLE_EXACT`; full `/book/info` metadata should be fetched before Edition identity is decided.

Likewise, `soldout=0` means the item is listed/not documented as sold out, but live validation should verify that this is a reasonable product-level proxy for “available in WeRead.” Do not overstate “readable” before that check.

## Provider boundary implemented

The first implementation now exists under:

```text
douban_weread/providers/weread/
  __init__.py
  client.py
```

Initial interface:

```python
class WeReadClient:
    def search_books(self, keyword: str, *, count: int = 10) -> list[WeReadSearchCandidate]: ...
    def get_book(self, book_id: str) -> Edition | None: ...
```

`WeReadSearchCandidate` retains lightweight search metadata including `book_id`, title, raw author, publisher, `soldout`, `deep_link`, `search_idx`, and source metadata.

The transport is injectable for tests. API transport and response parsing stay inside the provider; the existing resolver remains provider-agnostic.

## Read-only CLI implemented

The project command exposes a WeRead namespace through the top-level dispatcher:

```bash
douban-weread weread search "白夜行" --limit 5
douban-weread weread book --id 230107
```

`weread search` prints lightweight catalog candidates only. `weread book` performs a read-only `/book/info` lookup and prints normalized Edition metadata. Neither command mutates WeRead state, and neither assigns `AVAILABLE_EXACT` / `AVAILABLE_ALTERNATIVE` without resolver evidence.

## Error / safety boundary

- `WEREAD_API_KEY` is supplied locally only.
- Never print or persist the key.
- A missing or obviously malformed key fails before any network request.
- Non-2xx, non-zero gateway errors, malformed JSON, and documented `upgrade_info` responses fail explicitly rather than silently becoming `NOT_FOUND`.
- `NOT_FOUND` is a catalog/matching result, not a network-error fallback.
- No WeRead write operation is needed for v0.2.
- Do not reverse-engineer browser cookies or reader-content signatures for this search/status milestone while the official API covers the required read-only metadata.

## Regression coverage and local validation

`tests/test_weread.py` covers:

- missing / malformed API key fail-before-network behavior;
- explicit `scope=10` request construction;
- documented `scope=17` e-book response-group behavior;
- `soldout` parsing;
- cross-group `bookId` deduplication;
- blank searches without network traffic;
- `/book/info` normalization into the existing `Edition` model;
- raw person-field preservation;
- non-zero gateway errors;
- typed auth failures;
- `upgrade_info` fail-closed behavior;
- invalid JSON and non-2xx responses.

Additional CLI / dispatch tests cover the `weread search` command and top-level command routing.

The full local repository suite was rerun after the provider and first CLI commits:

```text
Ran 123 tests in 0.060s
OK
```

The editable package was then reinstalled and the installed console entry point was verified locally:

```text
usage: douban-weread weread [-h] {search} ...

Read-only WeRead search through Tencent's official Agent API.
```

## Live search validation — 2026-08-20

A user-bound API key was supplied only through the local `WEREAD_API_KEY` environment variable, then removed from the shell immediately after the request. The key value was not logged or committed.

One low-volume live search was executed:

```bash
douban-weread weread search "白夜行" --limit 5
```

Observed candidates:

```text
1. 白夜行
   Author: 东野圭吾
   WeRead bookId: 230107
   Sold out: no
   Deep link: https://weread.qq.com/book-detail?type=1&v=65032c105382db65050e7aa

2. 半小时讲透《白夜行》
   Author: 屈辛
   WeRead bookId: 3300189515
   Sold out: no

3. 恶意
   Author: 东野圭吾
   WeRead bookId: 3300020529
   Sold out: no

4. 解忧杂货店
   Author: 东野圭吾
   WeRead bookId: 3300020527
   Sold out: no

5. 白夜行者何平饭店
   Author: 鬼哭老朽
   WeRead bookId: 26855676
   Sold out: no
```

This live run validates that the official `/store/search` path works in the real runtime and that the provider correctly surfaces the expected title/author/bookId/soldout/deep-link fields. The exact-title candidate appears first as `bookId=230107`.

This does **not** yet prove exact Edition identity or full readability. The next evidence required is `/book/info` for `230107`, followed by comparison with the known Douban `白夜行` Editions through the existing resolver.

## Remaining milestone

1. Rerun the local test suite after the `weread book` CLI addition.
2. Fetch `/book/info` for live WeRead `bookId=230107`.
3. Compare that normalized WeRead Edition with known Douban `白夜行` Editions through the existing resolver.
4. Verify whether `soldout=0` is consistent with an actually openable/readable WeRead listing.
5. Only after live evidence confirms the semantics, wire `AVAILABLE_EXACT` / `AVAILABLE_ALTERNATIVE` into the cross-platform `ReadingIntent` flow.

## Live validation target

`白夜行` remains the first target because the Douban side already has multiple known Editions and the resolver behavior is understood. The remaining live validation should answer:

```text
What ISBN / translator / publisher / publishTime does /book/info return for bookId 230107?
Which known Douban Edition is it closest to?
Does compare_editions(Douban Edition, WeRead Edition) classify exact vs alternative correctly?
Is soldout consistent with an actually openable/readable WeRead listing?
```

Only after those facts are observed should the cross-platform `ReadingIntent` flow assign `AVAILABLE_EXACT` or `AVAILABLE_ALTERNATIVE` automatically.
