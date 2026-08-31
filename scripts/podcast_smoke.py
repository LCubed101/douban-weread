from __future__ import annotations

import argparse

from douban_weread.podcast_router import PodcastResolveKind, XiaoyuzhouEpisodeResolver
from douban_weread.providers.xiaoyuzhou import XiaoyuzhouAuthError, XiaoyuzhouProviderError


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Xiaoyuzhou podcast episode resolver smoke test")
    parser.add_argument("title", help="Episode title or search phrase")
    parser.add_argument("--podcast", help="Optional exact podcast title constraint")
    args = parser.parse_args()

    resolver = XiaoyuzhouEpisodeResolver()
    try:
        result = resolver.resolve(args.title, podcast=args.podcast)
    except XiaoyuzhouAuthError as exc:
        print(f"AUTH_REQUIRED · {exc}")
        print("Set XIAOYUZHOU_ACCESS_TOKEN locally; do not paste the token into chat or commit it to Git.")
        return
    except XiaoyuzhouProviderError as exc:
        print(f"PROVIDER_ERROR · {exc}")
        return

    if result.kind is PodcastResolveKind.EXACT and result.selected is not None:
        item = result.selected
        meta = " · ".join(x for x in (item.podcast_title, item.published_at) if x)
        print(f"EXACT · {item.title}" + (f" · {meta}" if meta else ""))
        print(item.episode_url)
        print("Read-only resolve completed. No Xiaoyuzhou state was modified.")
        return

    print(result.kind.value.upper())
    for index, item in enumerate(result.candidates, start=1):
        meta = " · ".join(x for x in (item.podcast_title, item.published_at) if x)
        print(f"{index}. {item.title}" + (f" · {meta}" if meta else ""))
        print(f"   {item.episode_url}")


if __name__ == "__main__":
    main()
