from __future__ import annotations

import unittest

from douban_weread.feishu_single_image_batch_guard import _credible_single_image_batch_title


class SingleImageBatchGuardTests(unittest.TestCase):
    def test_normal_book_titles_remain_credible(self) -> None:
        self.assertTrue(_credible_single_image_batch_title("精要主义"))
        self.assertTrue(_credible_single_image_batch_title("优秀校长一定要做的18件事"))

    def test_long_ocr_prose_is_rejected(self) -> None:
        value = (
            "精要作者：[英 The Disciplined Pursuit of Less 路雷戈·麦吉沃恩的百货城"
            "快来打造一座让所有时装新星啊，比如 TV 精要主义"
        )
        self.assertFalse(_credible_single_image_batch_title(value))

    def test_sentence_like_social_text_is_rejected(self) -> None:
        self.assertFalse(_credible_single_image_batch_title("作者：格雷戈·麦吉沃恩，比如这个版本很好"))


if __name__ == "__main__":
    unittest.main()
