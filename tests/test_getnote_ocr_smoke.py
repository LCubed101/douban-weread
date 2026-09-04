from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "getnote_ocr_smoke.py"
spec = importlib.util.spec_from_file_location("getnote_ocr_smoke", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class GetNoteOcrSmokeTests(unittest.TestCase):
    def test_upload_fields_accepts_direct_data_shape(self) -> None:
        host, access_url, fields = module._upload_fields(
            {
                "success": True,
                "data": {
                    "host": "https://oss.example",
                    "access_url": "https://cdn.example/a.jpg",
                    "object_key": "a.jpg",
                    "accessid": "access",
                    "policy": "policy",
                    "signature": "sig",
                    "callback": "cb",
                },
            }
        )
        self.assertEqual(host, "https://oss.example")
        self.assertEqual(access_url, "https://cdn.example/a.jpg")
        self.assertEqual([name for name, _ in fields], [
            "key",
            "OSSAccessKeyId",
            "policy",
            "signature",
            "callback",
        ])

    def test_upload_fields_accepts_nested_first_item_shape(self) -> None:
        host, access_url, _fields = module._upload_fields(
            {
                "data": {
                    "items": [
                        {
                            "host": "https://oss.example",
                            "access_url": "https://cdn.example/a.png",
                            "key": "a.png",
                            "OSSAccessKeyId": "access",
                            "policy": "policy",
                            "signature": "sig",
                            "callback": "cb",
                        }
                    ]
                }
            }
        )
        self.assertEqual(host, "https://oss.example")
        self.assertEqual(access_url, "https://cdn.example/a.png")

    def test_task_id_uses_documented_nested_location(self) -> None:
        self.assertEqual(
            module._task_id({"data": {"tasks": [{"task_id": "task-123"}]}}),
            "task-123",
        )

    def test_upload_fields_failure_only_reports_keys(self) -> None:
        with self.assertRaises(module.GetNoteSmokeError) as context:
            module._upload_fields({"data": {"host": "https://oss.example", "secret": "DO-NOT-PRINT"}})
        message = str(context.exception)
        self.assertIn("host", message)
        self.assertIn("secret", message)
        self.assertNotIn("DO-NOT-PRINT", message)


if __name__ == "__main__":
    unittest.main()
