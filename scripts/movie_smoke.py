from __future__ import annotations

import argparse

from douban_weread.movie_router import DoubanMovieResolver, MovieResolveKind
from douban_weread.providers.douban.movie_interest import DoubanMovieInterestClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve a Douban Movie title and optionally mark the exact subject 想看.")
    parser.add_argument("title")
    parser.add_argument("--write", action="store_true", help="Write 想看 only when the resolver found exactly one safe subject.")
    args = parser.parse_args()

    result = DoubanMovieResolver().resolve(args.title)
    if result.kind is MovieResolveKind.NOT_FOUND:
        print("NOT_FOUND")
        raise SystemExit(3)
    if result.kind is MovieResolveKind.AMBIGUOUS:
        print("AMBIGUOUS")
        for index, item in enumerate(result.candidates, start=1):
            suffix = " · ".join(x for x in (item.year, item.media_type, " / ".join(item.directors)) if x)
            print(f"{index}. {item.title}" + (f" · {suffix}" if suffix else "") + f" · {item.subject_url}")
        raise SystemExit(4)

    item = result.selected
    assert item is not None
    print(f"EXACT · {item.title} · {item.year or '-'} · {item.subject_url}")
    if not args.write:
        print("Read-only resolve completed. Re-run with --write only if this is the exact movie/TV subject you want to mark 想看.")
        return

    client = DoubanMovieInterestClient()
    mutation = client.mark_want_to_watch(item.douban_id, confirmed=True)
    print(f"WANT_TO_WATCH · verified={mutation.verified} · state={mutation.actual_status}")


if __name__ == "__main__":
    main()
