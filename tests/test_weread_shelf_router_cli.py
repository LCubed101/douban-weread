from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from douban_weread.weread_shelf_router_cli import run


class WeReadShelfRouterCliTests(unittest.TestCase):
    def test_parent_help_exposes_batch(self) -> None:
        stdout = io.StringIO()
        code = run(["--help"], stdout=stdout)
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("{sync,status,lookup,preview,queue,verify,batch,report,scan,worker}", output)
        self.assertIn("batch", output)
        self.assertIn("baseline-scoped checkpoints", output)
        self.assertIn("report", output)
        self.assertIn("persisted reconciliation evidence", output)

    def test_parent_help_exposes_scan(self) -> None:
        stdout = io.StringIO()
        code = run(["--help"], stdout=stdout)
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("scan", output)
        self.assertIn("visible progress", output)
        self.assertIn("read-only", output)

    def test_parent_help_exposes_worker(self) -> None:
        stdout = io.StringIO()
        code = run(["--help"], stdout=stdout)
        self.assertEqual(code, 0)
        output = stdout.getvalue()
        self.assertIn("worker", output)
        self.assertIn("first-login reconciliation worker", output)

    def test_batch_routes_without_leaking_batch_prefix(self) -> None:
        with patch("douban_weread.weread_shelf_batch_cli.run", return_value=0) as run_batch:
            code = run(["batch", "--direction", "weread-to-douban", "--limit", "2"])
        self.assertEqual(code, 0)
        run_batch.assert_called_once_with(["--direction", "weread-to-douban", "--limit", "2"])

    def test_report_routes_without_leaking_report_prefix(self) -> None:
        with patch("douban_weread.weread_shelf_report_cli.run", return_value=0) as run_report:
            code = run(["report", "--direction", "douban-to-weread", "--limit", "2"])
        self.assertEqual(code, 0)
        run_report.assert_called_once_with(["--direction", "douban-to-weread", "--limit", "2"])

    def test_scan_routes_without_leaking_scan_prefix(self) -> None:
        with patch("douban_weread.weread_shelf_scan_cli.run", return_value=0) as run_scan:
            code = run(["scan", "--direction", "both", "--max-items", "4"])
        self.assertEqual(code, 0)
        run_scan.assert_called_once_with(["--direction", "both", "--max-items", "4"])

    def test_worker_routes_without_leaking_worker_prefix(self) -> None:
        with patch("douban_weread.weread_shelf_worker_cli.run", return_value=0) as run_worker:
            code = run(["worker", "status"])
        self.assertEqual(code, 0)
        run_worker.assert_called_once_with(["status"])

    def test_existing_shelf_command_routes_unchanged(self) -> None:
        with patch("douban_weread.weread_shelf_cli.run", return_value=0) as run_shelf:
            code = run(["queue", "--limit", "5"])
        self.assertEqual(code, 0)
        run_shelf.assert_called_once_with(["queue", "--limit", "5"])


if __name__ == "__main__":
    unittest.main()
