from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_URL = "https://openapi.biji.com"


class GetNoteSmokeError(RuntimeError):
    pass


def _headers(*, json_body: bool = False) -> dict[str, str]:
    api_key = os.getenv("GETNOTE_API_KEY", "").strip()
    client_id = os.getenv("GETNOTE_CLIENT_ID", "").strip()
    if not api_key or not client_id:
        raise GetNoteSmokeError(
            "GETNOTE_API_KEY / GETNOTE_CLIENT_ID are not set. "
            "Export them locally; do not paste them into chat or commit them."
        )
    headers = {
        "Authorization": api_key,
        "X-Client-ID": client_id,
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def _json_request(method: str, path: str, *, query: dict[str, str] | None = None, payload: object | None = None) -> dict[str, Any]:
    url = BASE_URL + path
    if query:
        url += "?" + urlencode(query)
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=_headers(json_body=payload is not None), method=method)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GetNoteSmokeError(f"GetNote HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise GetNoteSmokeError(f"GetNote network error: {exc.reason}") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GetNoteSmokeError(f"GetNote returned non-JSON: {raw[:300]}") from exc
    if not isinstance(result, dict):
        raise GetNoteSmokeError("GetNote returned an unexpected response shape")
    if result.get("success") is False:
        raise GetNoteSmokeError(f"GetNote API error: {json.dumps(result, ensure_ascii=False)[:500]}")
    return result


def _first_mapping(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                return item
    return None


def _upload_fields(token_response: dict[str, Any]) -> tuple[str, str, list[tuple[str, str]]]:
    """Extract OSS host, access URL, and signed form fields defensively.

    The official docs define the required upload form field names but do not
    currently show a complete upload-token response example, so this parser
    accepts the common top-level / `data` / first-item shapes without logging
    signed credential values.
    """

    data = token_response.get("data", token_response)
    candidate = _first_mapping(data)
    if candidate is None:
        raise GetNoteSmokeError("Upload-token response has no usable data object")

    for key in ("items", "tokens", "uploads", "credentials"):
        nested = _first_mapping(candidate.get(key))
        if nested:
            candidate = {**candidate, **nested}
            break

    host = str(candidate.get("host") or candidate.get("upload_host") or "").strip()
    access_url = str(candidate.get("access_url") or candidate.get("url") or "").strip()
    object_key = str(candidate.get("object_key") or candidate.get("key") or "").strip()
    accessid = str(candidate.get("accessid") or candidate.get("OSSAccessKeyId") or "").strip()
    policy = str(candidate.get("policy") or "").strip()
    signature = str(candidate.get("signature") or "").strip()
    callback = str(candidate.get("callback") or "").strip()

    if not all((host, access_url, object_key, accessid, policy, signature, callback)):
        visible_keys = ", ".join(sorted(str(key) for key in candidate.keys()))
        raise GetNoteSmokeError(
            "Could not map upload-token response to the documented OSS fields. "
            f"Response keys: {visible_keys}. The script does not print credential values."
        )

    # Order is significant according to the official API documentation.
    fields = [
        ("key", object_key),
        ("OSSAccessKeyId", accessid),
        ("policy", policy),
        ("signature", signature),
        ("callback", callback),
    ]
    return host, access_url, fields


def _multipart_body(fields: list[tuple[str, str]], *, file_path: Path, content_type: str) -> tuple[bytes, str]:
    boundary = "----doubanweread-" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode(),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="Content-Type"\r\n\r\n',
            content_type.encode(),
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), boundary


def _upload_image(host: str, fields: list[tuple[str, str]], *, file_path: Path, content_type: str) -> None:
    body, boundary = _multipart_body(fields, file_path=file_path, content_type=content_type)
    request = Request(
        host,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GetNoteSmokeError(f"OSS upload HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise GetNoteSmokeError(f"OSS upload network error: {exc.reason}") from exc


def _task_id(save_response: dict[str, Any]) -> str:
    data = save_response.get("data") or {}
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if isinstance(tasks, list) and tasks and isinstance(tasks[0], dict):
        value = str(tasks[0].get("task_id") or "").strip()
        if value:
            return value
    raise GetNoteSmokeError("img_text save did not return data.tasks[0].task_id")


def run(file_path: Path, *, poll_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    suffix = file_path.suffix.lower().lstrip(".")
    mime_token = {"jpeg": "jpg"}.get(suffix, suffix)
    if mime_token not in {"jpg", "png", "gif", "webp"}:
        raise GetNoteSmokeError("Image must be jpg/jpeg/png/gif/webp")
    content_type = mimetypes.guess_type(file_path.name)[0] or f"image/{mime_token}"
    if content_type == "image/jpg":
        content_type = "image/jpeg"

    started = time.monotonic()
    token_response = _json_request(
        "GET",
        "/open/api/v1/resource/image/upload_token",
        query={"mime_type": mime_token, "count": "1"},
    )
    host, access_url, fields = _upload_fields(token_response)
    _upload_image(host, fields, file_path=file_path, content_type=content_type)

    save_response = _json_request(
        "POST",
        "/open/api/v1/resource/note/save",
        payload={
            "note_type": "img_text",
            "content": "Douban-Weread OCR smoke test",
            "image_urls": [access_url],
        },
    )
    task_id = _task_id(save_response)

    deadline = time.monotonic() + timeout_seconds
    note_id = ""
    status = "pending"
    polls = 0
    while time.monotonic() < deadline:
        progress = _json_request(
            "POST",
            "/open/api/v1/resource/note/task/progress",
            payload={"task_id": task_id},
        )
        polls += 1
        data = progress.get("data") if isinstance(progress.get("data"), dict) else {}
        status = str(data.get("status") or "").strip().casefold()
        if status == "success":
            note_id = str(data.get("note_id") or "").strip()
            break
        if status == "failed":
            raise GetNoteSmokeError("GetNote image-note task failed")
        time.sleep(poll_seconds)
    else:
        raise GetNoteSmokeError(f"Timed out after {timeout_seconds:g}s; last status={status or 'unknown'}")

    if not note_id:
        raise GetNoteSmokeError("Task succeeded but no note_id was returned")

    detail = _json_request(
        "GET",
        "/open/api/v1/resource/note/detail",
        query={"id": note_id},
    )
    data = detail.get("data") if isinstance(detail.get("data"), dict) else {}
    note = data.get("note") if isinstance(data.get("note"), dict) else {}
    return {
        "note_id": note_id,
        "title": note.get("title"),
        "content": note.get("content"),
        "note_type": note.get("note_type"),
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "polls": polls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test GetNote image OCR/AI analysis without changing the Feishu bot.")
    parser.add_argument("image", type=Path)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()

    image = args.image.expanduser().resolve()
    if not image.is_file():
        print(f"Image not found: {image}", file=sys.stderr)
        return 2
    if args.poll_seconds < 1:
        print("--poll-seconds must be >= 1", file=sys.stderr)
        return 2
    if args.timeout_seconds <= args.poll_seconds:
        print("--timeout-seconds must be greater than --poll-seconds", file=sys.stderr)
        return 2

    try:
        result = run(image, poll_seconds=args.poll_seconds, timeout_seconds=args.timeout_seconds)
    except GetNoteSmokeError as exc:
        print(f"ERROR · {exc}", file=sys.stderr)
        return 1

    print("GETNOTE_OCR_SMOKE · success")
    print(f"elapsed_seconds: {result['elapsed_seconds']}")
    print(f"polls: {result['polls']}")
    print(f"note_id: {result['note_id']}")
    print(f"note_type: {result['note_type'] or ''}")
    print("title:")
    print(result["title"] or "")
    print("content:")
    print(result["content"] or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
