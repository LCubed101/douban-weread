from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from douban_weread import entrypoint


class EntrypointTests(unittest.TestCase):
    def test_weread_capabilities_subcommand_routes_to_capability_cli(self) -> None:
        with (
            patch.object(sys, "argv", ["douban-weread", "weread", "capabilities"]),
            patch("douban_weread.weread_capabilities_cli.run", return_value=0) as run_capabilities,
        ):
            with self.assertRaises(SystemExit) as raised:
                entrypoint.main()

        self.assertEqual(raised.exception.code, 0)
        run_capabilities.assert_called_once_with([])

    def test_weread_subcommand_is_dispatched_without_leaking_prefix(self) -> None:
        with (
            patch.object(sys, "argv", ["douban-weread", "weread", "search", "白夜行", "--limit", "5"]),
            patch("douban_weread.weread_cli.run", return_value=0) as run_weread,
        ):
            with self.assertRaises(SystemExit) as raised:
                entrypoint.main()

        self.assertEqual(raised.exception.code, 0)
        run_weread.assert_called_once_with(["search", "白夜行", "--limit", "5"])

    def test_weread_shelf_subcommand_routes_to_shelf_router(self) -> None:
        with (
            patch.object(sys, "argv", ["douban-weread", "weread", "shelf", "lookup", "白夜行"]),
            patch("douban_weread.weread_shelf_router_cli.run", return_value=0) as run_shelf,
        ):
            with self.assertRaises(SystemExit) as raised:
                entrypoint.main()

        self.assertEqual(raised.exception.code, 0)
        run_shelf.assert_called_once_with(["lookup", "白夜行"])

    def test_weread_shelf_batch_prefix_is_preserved_for_router(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "douban-weread",
                    "weread",
                    "shelf",
                    "batch",
                    "--direction",
                    "weread-to-douban",
                    "--limit",
                    "2",
                ],
            ),
            patch("douban_weread.weread_shelf_router_cli.run", return_value=0) as run_shelf,
        ):
            with self.assertRaises(SystemExit) as raised:
                entrypoint.main()

        self.assertEqual(raised.exception.code, 0)
        run_shelf.assert_called_once_with(
            ["batch", "--direction", "weread-to-douban", "--limit", "2"]
        )

    def test_existing_commands_still_route_to_original_cli(self) -> None:
        with (
            patch.object(sys, "argv", ["douban-weread", "history", "status"]),
            patch("douban_weread.cli.main") as run_douban,
        ):
            entrypoint.main()

        run_douban.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
