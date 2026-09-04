# GetNote OCR Smoke Test

Goal: validate whether 得到大脑 / Get 笔记 can serve as the primary OCR + image-understanding provider for book screenshots before changing the Feishu runtime.

This is intentionally **not wired into the bot yet**.

## Official API flow

The smoke test follows the current GetNote OpenAPI image-note flow:

1. `GET /open/api/v1/resource/image/upload_token`
2. Upload the image to the returned OSS host with the returned signed fields, preserving field order.
3. `POST /open/api/v1/resource/note/save` with `note_type=img_text` and the returned `access_url`.
4. Poll `POST /open/api/v1/resource/note/task/progress` until success / failure.
5. Read `GET /open/api/v1/resource/note/detail?id=...` and print the note title/content plus elapsed time.

Current official docs say `img_text` is asynchronous and recommend 10–30 second polling intervals. For local validation the script defaults to 5 seconds so we can measure latency without changing the bot UX yet.

## Required scopes

The GetNote app needs at least:

- `note.image.upload`
- `note.content.write`
- `note.content.read`

## Local secrets

Do not commit credentials. Export them locally:

```bash
export GETNOTE_API_KEY='...'
export GETNOTE_CLIENT_ID='...'
```

The script never prints those values.

## Run

```bash
cd ~/douban-weread
source .venv/bin/activate
python scripts/getnote_ocr_smoke.py /absolute/path/to/screenshot.png
```

Optional controls:

```bash
python scripts/getnote_ocr_smoke.py screenshot.png --poll-seconds 5 --timeout-seconds 120
```

## First benchmark

Start with 10 real examples:

- 3 clean single-book covers
- 3 social/video screenshots containing one book
- 2 examples with very small publisher text
- 2 examples with noisy/complex backgrounds

Record:

- correct title: yes/no
- author recovered: yes/no
- publisher recovered: yes/no
- ISBN recovered: yes/no/not visible
- total latency
- whether the output contains social-screen noise mistaken for book metadata

Do not replace local RapidOCR yet. Promote GetNote to a runtime OCR provider only after this benchmark is materially better on publisher/ISBN recovery and acceptable on latency.
