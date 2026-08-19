# Roadmap

## v0.1 — Capture to Douban

Goal: identify a book accurately and mark the intended Douban edition as “Want to Read” without downgrading or duplicating existing reading history.

- [ ] Define Work / Edition / ReadingIntent models
- [ ] Search Douban by title
- [ ] Search Douban by ISBN
- [ ] Resolve likely edition from image/text clues
- [ ] Authenticate Douban using user-owned credentials/cookies
- [ ] Read current Douban state for an exact subject
- [ ] Discover same-Work editions before mutation
- [ ] Prevent `READ` / `READING` from being downgraded to `WISH`
- [ ] Detect other-edition `WISH` as an edition mismatch
- [ ] Build a local Douban reading-history index from the user's WISH / READING / READ lists
- [ ] Mark the selected Douban edition as `wish` only after reconciliation
- [ ] Verify the saved state after every write
- [ ] Add Feishu bot input for image/text/link
- [ ] Keep secrets out of the repository

## v0.2 — WeRead Discovery

Goal: determine what edition is actually available on WeRead and what provider-visible reading state exists there.

- [ ] Search WeRead by title / author / ISBN where possible
- [ ] Verify which reading / shelf states WeRead actually exposes
- [ ] Classify `AVAILABLE_EXACT`
- [ ] Classify `AVAILABLE_ALTERNATIVE`
- [ ] Classify `COMING_SOON`
- [ ] Classify `NOT_FOUND`
- [ ] Store platform-specific identifiers and metadata

## v0.3 — Cross-Platform Reconciliation & Edition Alignment

Goal: make Douban and WeRead point to the same practical reading edition without erasing prior reading history.

- [ ] Compare translator, publisher, publication date and ISBN
- [ ] Preserve Source Edition separately from Selected Edition
- [ ] Preserve per-platform reading state per Edition
- [ ] Detect already-read / reread cases before alignment
- [ ] Detect state mismatch separately from edition mismatch
- [ ] Require confirmation for materially different translations/editions
- [ ] Update Douban wish to the Selected Edition only when reconciliation allows it
- [ ] Add / open the Selected Edition in WeRead where technically supported
- [ ] Record resolution reason and confidence

## v0.4 — Availability Monitoring

- [ ] Subscribe to WeRead coming-soon reminders where technically supported
- [ ] Recheck `NOT_FOUND` books periodically
- [ ] Notify users only when status changes
- [ ] Support Feishu push notifications

## v0.5 — More Interfaces

- [ ] Web UI
- [ ] CLI
- [ ] Telegram bot
- [ ] macOS Shortcut / Share Sheet
- [ ] Pluggable notification channels

## Engineering principles

- Self-hosted first
- Work and Edition are separate entities
- Reading state belongs to a specific platform + Edition and should be preserved
- Known `READ` / `READING` state must not be silently downgraded to `WISH`
- No title-only destructive matching
- Preserve original discovery context
- Prefer explicit user confirmation over silent edition substitution when meaning may change
- Clearly label unofficial APIs / reverse-engineered interfaces
- Credit upstream projects and comply with their licenses
