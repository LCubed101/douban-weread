# V1.2 Movie Router smoke command

After pulling this branch into a local checkout with your own `DOUBAN_COOKIE`:

```bash
python scripts/movie_smoke.py "机器人之梦"
```

This first command is read-only. It should print one of `EXACT`, `AMBIGUOUS`, or `NOT_FOUND`.

Only after visually confirming the exact Douban Movie subject, opt into the write:

```bash
python scripts/movie_smoke.py "机器人之梦" --write
```

A successful verified write ends with:

```text
WANT_TO_WATCH · verified=True · state=wish
```

The smoke script deliberately refuses to write when the resolver returns multiple same-name subjects.
