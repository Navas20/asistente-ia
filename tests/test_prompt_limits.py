from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

import main


class PromptLimitsTests(unittest.TestCase):
    def test_prepare_history_for_prompt_limits_history_and_chars(self):
        history = [
            {"role": "user", "content": "x" * 3000},
            {"role": "assistant", "content": "y" * 3000},
            {"role": "user", "content": "z" * 3000},
        ]

        prepared = main._prepare_history_for_prompt(history, limit=2, max_chars=200)

        self.assertEqual(len(prepared), 2)
        self.assertTrue(prepared[0]["content"].endswith("..."))
        self.assertLessEqual(len(prepared[0]["content"]), 200)
        self.assertTrue(prepared[-1]["content"].endswith("..."))

    def test_format_memories_limits_items_and_chars(self):
        memories = {f"m{i}": "x" * 1000 for i in range(10)}
        block = main.format_memories(memories, max_items=3, max_chars=120)

        self.assertTrue("M0" in block or "M1" in block or "M2" in block)
        self.assertTrue("M3" not in block)


if __name__ == "__main__":
    unittest.main()
