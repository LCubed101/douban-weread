# WeRead Waiting List V1.1

When a recommendation is not currently readable in WeRead, keep it as a durable watch instead of ending the flow.

## States and cadence

- `waiting`: an exact/same-work WeRead item is known but is currently unavailable. Recheck after 30 days.
- `not_found`: no safe WeRead entity can currently be resolved. Recheck after 90 days.
- `available`: a later check found a readable WeRead edition; notify the originating Feishu chat once.

Each entry records its first-seen time, last check time, check count, next check time, and watch kind.

The background loop may wake more often, but only entries whose `next_check_at` is due should call WeRead again.

For title-only Reading Inbox items (for example books extracted from flomo screenshots), rechecks should use the title-only resolver rather than the conservative Edition-to-Edition matcher.
