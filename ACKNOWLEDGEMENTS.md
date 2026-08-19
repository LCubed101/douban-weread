# Acknowledgements

This project is built with gratitude to the open-source community.

The projects below have informed the early research and architecture of `douban-weread`. References here do **not** imply affiliation, endorsement, or that code has been copied directly.

## Douban ecosystem

- **DouBanSync** — referenced for its approach to authenticated Douban operations using browser cookies, `ck` / `dbcl2`, and internal interest endpoints.
- **tofu (doufen-org/tofu)** — referenced as an implementation/protocol reference for cross-media Douban interest states, including the Book interest endpoint and the `wish` / `do` / `collect` state names.
- **douban-mcp** — referenced for Douban book search, ISBN lookup, and exploration of Douban/Frodo API access patterns.
- **doumark-action** — referenced for ideas around synchronizing Douban mark states and scheduled jobs.

## WeRead ecosystem

- **weread-mcp** — referenced for WeRead search, bookshelf, and tool-integration ideas.
- **weread-master** — referenced for book resolution and WeRead integration patterns.
- **LifeInk** — referenced for authenticated WeRead browser automation and cross-service reading workflows.

## Attribution policy

We distinguish between:

1. **Inspiration** — product or architectural ideas only.
2. **Implementation reference** — behavior or protocol studied and reimplemented independently.
3. **Direct code reuse / dependency** — code or packages incorporated into this repository.

If direct code reuse occurs, the relevant copyright notices and license obligations must be preserved. Such reuse should also be documented in `THIRD_PARTY_NOTICES.md`.

Thank you to the maintainers and contributors of these projects for making their work available to the community.
