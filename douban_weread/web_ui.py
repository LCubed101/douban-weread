from __future__ import annotations

import argparse
import html
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, quote, urlparse

from douban_weread.reconciliation import (
    ProductActionKind,
    ProductReconciliationBucket,
    ProductReconciliationView,
    build_product_reconciliation_view,
    build_reconciliation_action_inbox,
    build_reconciliation_home_model,
    get_reconciliation_detail,
)
from douban_weread.storage import (
    ReadingHistoryIndex,
    ReconciliationEvidenceStore,
    ReconciliationWorkerStateStore,
    WeReadShelfIndex,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


_CSS = r"""
:root {
  color-scheme: light;
  --bg: #f7f7f5;
  --card: #ffffff;
  --text: #171717;
  --muted: #6d6d67;
  --line: #e7e7e2;
  --accent: #1877f2;
  --accent-soft: #eaf3ff;
  --warn: #8a5a00;
  --warn-soft: #fff6df;
  --ok: #216e39;
  --ok-soft: #ebf7ee;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", sans-serif;
  line-height: 1.5;
}
a { color: inherit; text-decoration: none; }
.shell { max-width: 760px; margin: 0 auto; padding: 40px 20px 72px; }
.brand { font-size: 14px; color: var(--muted); margin-bottom: 28px; }
h1 { margin: 0 0 8px; font-size: 30px; line-height: 1.2; letter-spacing: -0.02em; }
h2 { margin: 0; font-size: 19px; }
.subtle { color: var(--muted); }
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 22px;
  margin-top: 16px;
}
.progress-row { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
.progress-number { font-size: 22px; font-weight: 700; }
.progress-track { height: 8px; background: #ecece8; border-radius: 999px; overflow: hidden; margin: 16px 0 8px; }
.progress-fill { height: 100%; background: var(--text); min-width: 3px; border-radius: inherit; }
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 16px; }
.stat { background: #fafaf8; border-radius: 14px; padding: 14px; }
.stat strong { display: block; font-size: 22px; }
.stat span { color: var(--muted); font-size: 13px; }
.button {
  display: inline-flex; align-items: center; justify-content: center;
  min-height: 44px; padding: 0 16px; border-radius: 12px;
  background: var(--text); color: white; font-weight: 650; margin-top: 16px;
}
.button.secondary { background: white; color: var(--text); border: 1px solid var(--line); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin: 28px 0 10px; }
.section-count { color: var(--muted); font-size: 14px; }
.list { display: flex; flex-direction: column; gap: 10px; }
.item { background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 18px; }
.item-top { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; }
.item-title { font-size: 17px; font-weight: 680; }
.item-target { color: var(--muted); margin-top: 4px; }
.badge { display: inline-block; font-size: 12px; padding: 4px 8px; border-radius: 999px; white-space: nowrap; }
.badge.review { background: var(--warn-soft); color: var(--warn); }
.badge.add { background: var(--accent-soft); color: #1459a8; }
.badge.ok { background: var(--ok-soft); color: var(--ok); }
.meta { margin-top: 12px; color: var(--muted); font-size: 13px; }
.back { color: var(--muted); font-size: 14px; display: inline-block; margin-bottom: 22px; }
.compare { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 18px; }
.compare-card { background: #fafaf8; border-radius: 14px; padding: 16px; }
.compare-label { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.compare-title { font-weight: 680; font-size: 17px; }
.notice { background: var(--warn-soft); border-radius: 14px; padding: 16px; margin-top: 16px; }
.notice strong { display: block; margin-bottom: 4px; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; }
.empty { text-align: center; color: var(--muted); padding: 48px 20px; }
.footer { color: var(--muted); font-size: 12px; margin-top: 28px; }
@media (max-width: 560px) {
  .shell { padding-top: 24px; }
  .stats, .compare { grid-template-columns: 1fr; }
  h1 { font-size: 26px; }
}
"""


def build_local_product_view() -> ProductReconciliationView:
    return build_product_reconciliation_view(
        shelf_provider=WeReadShelfIndex(),
        history_provider=ReadingHistoryIndex(),
        evidence_provider=ReconciliationEvidenceStore(),
        state_provider=ReconciliationWorkerStateStore(),
    )


def render_home(view: ProductReconciliationView) -> str:
    home = build_reconciliation_home_model(view)
    if home.candidate_total is None or home.verified_total is None:
        main = """
        <h1>正在准备阅读记录</h1>
        <p class="subtle">需要先建立完整的豆瓣与微信读书本地基线。</p>
        """
        return _page("豆瓣 × 微信读书", main)

    ratio = 0.0 if not home.candidate_total else home.verified_total / home.candidate_total
    width = min(100.0, max(0.0, ratio * 100.0))
    need_action = home.requires_user_action_total or 0
    aligned = home.aligned_total or 0
    no_action = home.no_user_action_total or 0
    pending = home.pending_total or 0
    progress_label = _e(home.progress_label or "0%")

    action_link = (
        f'<a class="button" href="/inbox">查看待处理 {need_action}</a>'
        if need_action
        else '<span class="button secondary">目前没有待处理项目</span>'
    )
    main = f"""
    <h1>正在比较你的阅读记录</h1>
    <p class="subtle">只对已经验证的项目给出结论，尚未验证的项目会继续保持待比较。</p>
    <section class="card">
      <div class="progress-row">
        <div class="progress-number">{home.verified_total} / {home.candidate_total}</div>
        <div class="subtle">{progress_label}</div>
      </div>
      <div class="progress-track"><div class="progress-fill" style="width:{width:.3f}%"></div></div>
      <div class="subtle">{pending} 本还在比较中</div>
      <div class="stats">
        <div class="stat"><strong>{need_action}</strong><span>待你处理</span></div>
        <div class="stat"><strong>{aligned}</strong><span>已对齐</span></div>
        <div class="stat"><strong>{no_action}</strong><span>无需处理</span></div>
      </div>
      {action_link}
    </section>
    <section class="card">
      <h2>当前已验证结果</h2>
      <div class="stats">
        <div class="stat"><strong>{home.review_total}</strong><span>需要确认</span></div>
        <div class="stat"><strong>{home.add_to_weread_total}</strong><span>可在微信读书打开</span></div>
        <div class="stat"><strong>{home.suggest_douban_state_total}</strong><span>建议更新豆瓣状态</span></div>
      </div>
    </section>
    """
    return _page("豆瓣 × 微信读书", main)


def render_inbox(view: ProductReconciliationView) -> str:
    inbox = build_reconciliation_action_inbox(view)
    if inbox.total == 0:
        main = '<a class="back" href="/">← 返回首页</a><h1>待处理</h1><div class="empty">目前没有需要你处理的项目。</div>'
        return _page("待处理", main)

    blocks: list[str] = ['<a class="back" href="/">← 返回首页</a>', f'<h1>待处理 {inbox.total}</h1>']
    labels = {
        ProductReconciliationBucket.REVIEW: "需要确认",
        ProductReconciliationBucket.ADD_TO_WEREAD: "可在微信读书打开",
        ProductReconciliationBucket.SUGGEST_DOUBAN_STATE: "建议更新豆瓣状态",
    }
    for section in inbox.sections:
        blocks.append(
            f'<div class="section-head"><h2>{_e(labels.get(section.bucket, section.bucket.value))}</h2>'
            f'<span class="section-count">{section.count}</span></div><div class="list">'
        )
        for item in section.items:
            target = f'<div class="item-target">微信读书：{_e(item.selected_edition_title)}</div>' if item.selected_edition_title else ""
            detail_url = "/detail?direction=" + quote(item.direction, safe="") + "&item_id=" + quote(item.item_id, safe="")
            badge_class, badge_text = _inbox_badge(item.action_kind)
            blocks.append(
                f'<a class="item" href="{detail_url}"><div class="item-top">'
                f'<div><div class="item-title">{_e(item.title)}</div>{target}</div>'
                f'<span class="badge {badge_class}">{_e(badge_text)}</span></div>'
                f'<div class="meta">{_e(_localized_summary(item.action_kind))}</div></a>'
            )
        blocks.append("</div>")
    return _page("待处理", "".join(blocks))


def render_detail(view: ProductReconciliationView, *, direction: str, item_id: str) -> tuple[int, str]:
    detail = get_reconciliation_detail(view, direction=direction, item_id=item_id)
    if detail is None:
        return HTTPStatus.NOT_FOUND, _page(
            "未找到",
            '<a class="back" href="/inbox">← 返回待处理</a><h1>这个项目还没有可展示的验证结果</h1>'
            '<p class="subtle">未验证项目不会被提前生成详情。</p>',
        )

    target_title = detail.selected_edition_title or detail.title
    source_state = _douban_state_label(detail.source_state)
    shelf = _shelf_label(detail.shelf_membership)
    notice_title, notice_body = _detail_notice(detail.action_kind)
    action_html = _detail_actions(detail.action_kind, detail.deep_link)

    main = f"""
    <a class="back" href="/inbox">← 返回待处理</a>
    <h1>{_e(_detail_title(detail.action_kind))}</h1>
    <p class="subtle">{_e(detail.title)}</p>
    <section class="card">
      <div class="compare">
        <div class="compare-card">
          <div class="compare-label">豆瓣中的版本</div>
          <div class="compare-title">{_e(detail.title)}</div>
          <div class="meta">状态：{_e(source_state)}</div>
        </div>
        <div class="compare-card">
          <div class="compare-label">微信读书找到的版本</div>
          <div class="compare-title">{_e(target_title)}</div>
          <div class="meta">当前书架：{_e(shelf)}</div>
        </div>
      </div>
      <div class="notice"><strong>{_e(notice_title)}</strong>{_e(notice_body)}</div>
      <div class="meta">
        匹配类型：{_e(detail.match_kind or "—")}<br>
        微信读书 bookId：{_e(detail.weread_book_id or "—")}
      </div>
      <div class="actions">{action_html}<a class="button secondary" href="/inbox">暂不处理</a></div>
    </section>
    """
    return HTTPStatus.OK, _page(_detail_title(detail.action_kind), main)


def make_handler(view_factory: Callable[[], ProductReconciliationView] = build_local_product_view):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            parsed = urlparse(self.path)
            try:
                view = view_factory()
                if parsed.path == "/":
                    self._send(HTTPStatus.OK, render_home(view))
                    return
                if parsed.path == "/inbox":
                    self._send(HTTPStatus.OK, render_inbox(view))
                    return
                if parsed.path == "/detail":
                    query = parse_qs(parsed.query)
                    direction = (query.get("direction") or [""])[0]
                    item_id = (query.get("item_id") or [""])[0]
                    if not direction or not item_id:
                        self._send(HTTPStatus.BAD_REQUEST, _page("参数错误", "<h1>缺少详情参数</h1>"))
                        return
                    status, body = render_detail(view, direction=direction, item_id=item_id)
                    self._send(status, body)
                    return
                self._send(HTTPStatus.NOT_FOUND, _page("未找到", "<h1>页面不存在</h1>"))
            except Exception as exc:  # fail closed at the UI boundary
                self._send(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    _page(
                        "无法显示",
                        "<h1>暂时无法安全显示本地结果</h1>"
                        f'<p class="subtle">{_e(type(exc).__name__)}：{_e(str(exc))}</p>',
                    ),
                )

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, status: int, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="douban-weread-ui",
        description="Open the local-only Douban × WeRead reconciliation UI.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host (default: {DEFAULT_HOST}).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port (default: {DEFAULT_PORT}).")
    parser.add_argument("--no-open", action="store_true", help="Do not automatically open the browser.")
    return parser


def run(argv: list[str] | None = None, *, stdout=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    if args.host != DEFAULT_HOST:
        print("Refusing to bind beyond 127.0.0.1 in V1. This UI is local-only.", file=stdout)
        return 2
    if not 1 <= args.port <= 65535:
        print("Port must be between 1 and 65535.", file=stdout)
        return 2

    server = ThreadingHTTPServer((args.host, args.port), make_handler())
    url = f"http://{args.host}:{args.port}/"
    print(f"Douban × WeRead local UI: {url}", file=stdout)
    print("Local-only: reads the local reconciliation database; no provider API or platform mutation.", file=stdout)
    print("Press Ctrl-C to stop.", file=stdout)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main() -> None:
    raise SystemExit(run())


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<main class="shell">
  <div class="brand">豆瓣 × 微信读书 · 本地对齐</div>
  {body}
  <div class="footer">本页面只展示当前已验证的本地证据。待验证项目不会被提前分类。</div>
</main>
</body>
</html>"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _inbox_badge(action: ProductActionKind) -> tuple[str, str]:
    if action in {
        ProductActionKind.REVIEW_EDITION,
        ProductActionKind.REVIEW_IDENTITY,
        ProductActionKind.REVIEW_REREAD,
        ProductActionKind.REVIEW_STATE,
    }:
        return "review", "需要确认"
    if action is ProductActionKind.OPEN_WEREAD:
        return "add", "去微信读书"
    if action is ProductActionKind.UPDATE_DOUBAN_STATE:
        return "add", "更新豆瓣"
    return "ok", "无需处理"


def _localized_summary(action: ProductActionKind) -> str:
    mapping = {
        ProductActionKind.REVIEW_EDITION: "找到同一作品的其他版本，需要你确认版本。",
        ProductActionKind.REVIEW_IDENTITY: "目前证据不足以安全确认是同一作品，需要你确认。",
        ProductActionKind.REVIEW_REREAD: "豆瓣已读，但微信读书显示正在阅读，可能是在重读。",
        ProductActionKind.REVIEW_STATE: "两边阅读状态存在不确定或冲突，需要你确认。",
        ProductActionKind.OPEN_WEREAD: "已找到可读版本，但还不在当前微信读书书架。",
        ProductActionKind.UPDATE_DOUBAN_STATE: "微信读书已有明确阅读状态，可考虑更新豆瓣状态。",
    }
    return mapping.get(action, "")


def _detail_title(action: ProductActionKind) -> str:
    mapping = {
        ProductActionKind.REVIEW_EDITION: "确认版本",
        ProductActionKind.REVIEW_IDENTITY: "确认是不是同一本书",
        ProductActionKind.REVIEW_REREAD: "确认是否正在重读",
        ProductActionKind.REVIEW_STATE: "确认阅读状态",
        ProductActionKind.OPEN_WEREAD: "在微信读书查看",
        ProductActionKind.UPDATE_DOUBAN_STATE: "确认豆瓣状态",
    }
    return mapping.get(action, "查看详情")


def _detail_notice(action: ProductActionKind) -> tuple[str, str]:
    mapping = {
        ProductActionKind.REVIEW_EDITION: (
            "为什么需要确认？",
            "这是同一部作品，但不是已验证的同一版本。在确认前，我们不会把它当成同一个版本自动处理。",
        ),
        ProductActionKind.REVIEW_IDENTITY: (
            "为什么需要确认？",
            "当前标题或元数据相似，但证据还不足以安全确认作品身份。",
        ),
        ProductActionKind.REVIEW_REREAD: (
            "可能正在重读",
            "豆瓣已经记录为读过，而微信读书显示正在阅读。我们不会自动降低豆瓣历史状态。",
        ),
        ProductActionKind.REVIEW_STATE: (
            "阅读状态需要确认",
            "至少一侧状态不明确或互相冲突，因此不会自动同步。",
        ),
        ProductActionKind.OPEN_WEREAD: (
            "已经找到可读版本",
            "当前只提供打开微信读书的入口；V1 不会自动把书加入你的微信读书书架。",
        ),
        ProductActionKind.UPDATE_DOUBAN_STATE: (
            "可以考虑更新豆瓣状态",
            "这是建议，不是自动写入。真正修改豆瓣前仍需要明确确认。",
        ),
    }
    return mapping.get(action, ("当前结果", "这是当前已验证的本地对齐结果。"))


def _detail_actions(action: ProductActionKind, deep_link: str | None) -> str:
    if action is ProductActionKind.OPEN_WEREAD and deep_link:
        return f'<a class="button" href="{_e(deep_link)}" target="_blank" rel="noreferrer">在微信读书查看</a>'
    if action is ProductActionKind.REVIEW_EDITION and deep_link:
        return f'<a class="button" href="{_e(deep_link)}" target="_blank" rel="noreferrer">在微信读书查看</a>'
    if action is ProductActionKind.UPDATE_DOUBAN_STATE:
        return '<span class="button secondary">V1 暂不自动写入豆瓣</span>'
    return ""


def _douban_state_label(value: str | None) -> str:
    return {"wish": "想读", "do": "在读", "collect": "读过"}.get(value or "", value or "未知")


def _shelf_label(value: str | None) -> str:
    return {"yes": "已加入", "no": "未加入", "unresolved": "未确认"}.get(value or "", value or "未知")


if __name__ == "__main__":
    main()
