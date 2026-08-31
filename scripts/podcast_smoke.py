from __future__ import annotations

import argparse
import os

from douban_weread.podcast_router import PodcastResolveKind, XiaoyuzhouEpisodeResolver
from douban_weread.providers.xiaoyuzhou import XiaoyuzhouAuthError, XiaoyuzhouProviderError
from douban_weread.xiaoyuzhou_auth import XiaoyuzhouRefreshError, load_or_refresh_access_token


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Xiaoyuzhou podcast episode resolver smoke test")
    parser.add_argument("title", help="Episode title or search phrase")
    parser.add_argument("--podcast", help="Optional exact podcast title constraint")
    parser.add_argument(
        "--refresh-token-file",
        help="Optional local file containing a Xiaoyuzhou refresh token. The token may rotate and is written back privately.",
    )
    args = parser.parse_args()

    if not os.getenv("XIAOYUZHOU_ACCESS_TOKEN", "").strip():
        try:
            access = load_or_refresh_access_token(token_file=args.refresh_token_file)
        except XiaoyuzhouRefreshError as exc:
            print(f"AUTH_REQUIRED · {exc}")
            print(
                "Use a local refresh-token file (recommended) or XIAOYUZHOU_ACCESS_TOKEN. "
                "Do not paste either token into chat or commit it to Git."
            )
            return
        os.environ["XIAOYUZHOU_ACCESS_TOKEN"] = access

    resolver = XiaoyuzhouEpisodeResolver()
    try:
        result = resolver.resolve(args.title, podcast=args.podcast)
    except XiaoyuzhouAuthError as exc:
        print(f"AUTH_REQUIRED · {exc}")
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
