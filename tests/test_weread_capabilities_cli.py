from __future__ import annotations

import io
import unittest
from unittest.mock import patch

from douban_weread.weread_capabilities import WeReadCapability
from douban_weread.weread_capabilities_cli import run


class WeReadCapabilitiesCliTests(unittest.TestCase):
    def test_lists_available_apis_and_flags_write_like_names(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch(
            "douban_weread.weread_capabilities_cli.WeReadCapabilityDiscovery.list_capabilities",
            return_value=(
                WeReadCapability("/store/search"),
                WeReadCapability("/shelf/sync"),
                WeReadCapability("/shelf/addBook", "add one book"),
            ),
        ):
            code = run([], stdout=stdout, stderr=stderr)
        self.assertEqual(code, 0)
        self.assertIn("/store/search", stdout.getvalue())
        self.assertIn("Potential subscription/shelf-write APIs detected", stdout.getvalue())
        self.assertIn("/shelf/addbook", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_rejects_extra_arguments(self) -> None:
        stderr = io.StringIO()
        code = run(["extra"], stderr=stderr)
        self.assertEqual(code, 2)
        self.assertIn("Usage", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
