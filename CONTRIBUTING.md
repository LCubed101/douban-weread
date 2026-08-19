# Contributing

Thanks for contributing to `douban-weread`.

## Principles

- Keep Work and Edition separate.
- Do not use title-only matching for destructive or state-changing actions.
- Preserve Source Edition even when Selected Edition changes.
- Ask for user confirmation when translator, language, abridgement, or revision differences may materially affect the reading experience.
- Keep providers modular: Douban, WeRead, Feishu, and future interfaces should remain replaceable adapters.
- Never commit cookies, tokens, API keys, or other user secrets.
- Clearly label unofficial / reverse-engineered interfaces.

## Upstream attribution

If your contribution is inspired by or based on another open-source project:

1. Add or update `ACKNOWLEDGEMENTS.md` for inspiration or implementation references.
2. Add or update `THIRD_PARTY_NOTICES.md` for direct code reuse or dependencies that require notices.
3. Preserve all upstream copyright and license requirements.
4. Do not describe independently implemented behavior as copied code.

## Development workflow

Prefer small, focused pull requests. Include tests for matching and edition-resolution logic where possible.
