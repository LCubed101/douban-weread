from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace

from douban_weread.core.models import Edition
from douban_weread.inbox_wish import DoubanWishFlow, WishFlowKind


class FakeSearch:
    def __init__(self) -> None:
        self.edition = Edition(
            title="测试书",
            authors=["作者"],
            isbn="9780000000001",
            douban_id="100",
        )

    def get_by_subject_id(self, subject_id: str) -> Edition | None:
        return self.edition if subject_id == "100" else None

    def search_by_title(self, title: str, *, count: int = 20) -> list[Edition]:
        return [self.edition]


class FakeInterest:
    def __init__(self, status: str | None = None) -> None:
        self.status = status
        self.status_calls: list[str] = []
        self.mark_calls: list[tuple[str, bool]] = []

    def get_interest_status(self, subject_id: str) -> str | None:
        self.status_calls.append(subject_id)
        return self.status

    def mark_wish(self, subject_id: str, *, confirmed: bool = False):
        self.mark_calls.append((subject_id, confirmed))
        self.status = "wish"
        return SimpleNamespace(subject_id=subject_id, verified=True)


@dataclass
class FakeHistoryStatus:
    complete: bool = True


class FakeHistory:
    def __init__(self) -> None:
        self.states: list[tuple[str, str, str]] = []

    def status(self) -> FakeHistoryStatus:
        return FakeHistoryStatus()

    def find_title_candidates(
        self,
        title: str,
        *,
        limit: int = 30,
        min_similarity: float = 0.72,
    ) -> list[object]:
        return []

    def set_state(self, subject_id: str, title: str, state: str) -> None:
        self.states.append((subject_id, title, state))


class DoubanWishFlowTests(unittest.TestCase):
    def test_preflight_is_read_only(self) -> None:
        interest = FakeInterest()
        history = FakeHistory()
        flow = DoubanWishFlow(FakeSearch(), interest, history)

        result = flow.preflight("100")

        self.assertEqual(result.kind, WishFlowKind.READY)
        self.assertEqual(result.title, "测试书")
        self.assertEqual(interest.mark_calls, [])
        self.assertEqual(history.states, [])

    def test_commit_rechecks_then_writes_with_explicit_confirmation(self) -> None:
        interest = FakeInterest()
        history = FakeHistory()
        flow = DoubanWishFlow(FakeSearch(), interest, history)

        result = flow.commit("100")

        self.assertEqual(result.kind, WishFlowKind.WRITTEN)
        self.assertEqual(interest.mark_calls, [("100", True)])
        self.assertGreaterEqual(len(interest.status_calls), 1)
        self.assertEqual(history.states, [("100", "测试书", "wish")])

    def test_already_wish_is_noop(self) -> None:
        interest = FakeInterest("wish")
        history = FakeHistory()
        flow = DoubanWishFlow(FakeSearch(), interest, history)

        result = flow.commit("100")

        self.assertEqual(result.kind, WishFlowKind.ALREADY_WISH)
        self.assertEqual(interest.mark_calls, [])
        self.assertEqual(history.states, [])


if __name__ == "__main__":
    unittest.main()
