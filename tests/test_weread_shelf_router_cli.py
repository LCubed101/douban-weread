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
        self.assertIn("{sync,status,lookup,preview,queue,verify,batch}", output)
        self.assertIn("batch", output)
        self.assertIn("baseline-scoped checkpoints", output)

    def test_batch_routes_without_leaking_batch_prefix(self) -> None:
        with patch("douban_weread.weread_shelf_batch_cli.run", return_value=0) as run_batch:
            code = run(["batch", "--direction", "weread-to-douban", "--limit", "2"])
        self.assertEqual(code, 0)
        run_batch.assert_called_once_with(["--direction", "weread-to-douban", "--limit", "2"])

    def test_existing_shelf_command_routes_unchanged(self) -> None:
        with patch("douban_weread.weread_shelf_cli.run", return_value=0) as run_shelf:
            code = run(["queue", "--limit", "5"])
        self.assertEqual(code, 0)
        run_shelf.assert_called_once_with(["queue", "--limit", "5"])


if __name__ == "__main__":
    unittest.main()
