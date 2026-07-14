from pathlib import Path
import threading
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from task_queue import TaskQueue


def make_queue():
    queue = TaskQueue.__new__(TaskQueue)
    queue.max_concurrent = 3
    queue._tasks = {}
    queue._queue = []
    queue._active = 1
    queue._lock = threading.Lock()
    queue._save = Mock()
    return queue


class TaskQueueToolTests(unittest.TestCase):
    def test_run_task_dispatches_tool_type_to_generic_handler(self):
        queue = make_queue()
        queue._run_tool_task = Mock()
        queue._run_playbook_task = Mock()

        queue._run_task(
            "ABC123",
            {
                "type": "tool",
                "target": "example.com",
                "params": {"tool": "whois"},
            },
        )

        queue._run_tool_task.assert_called_once_with(
            "ABC123", "example.com", {"tool": "whois"}
        )
        queue._run_playbook_task.assert_not_called()

    def test_cancelled_task_is_not_overwritten_by_completion(self):
        queue = make_queue()
        queue._tasks["ABC123"] = {"status": "cancelled"}

        queue.complete("ABC123", {"success": True})

        self.assertEqual(queue._tasks["ABC123"]["status"], "cancelled")

    def test_generic_tool_task_fails_on_nonzero_tool_result(self):
        queue = make_queue()
        queue._tasks["ABC123"] = {"status": "running"}
        result = Mock()
        result.success = False
        result.error = ""
        result.stderr = "invalid option"
        result.exit_code = 2
        result.to_dict.return_value = {"success": False, "exit_code": 2}

        fake_engine = Mock()
        fake_engine.run_tool.return_value = result
        with patch.dict(
            sys.modules,
            {"tools_engine": Mock(tools_engine=fake_engine)},
        ):
            queue._run_tool_task(
                "ABC123",
                "example.com",
                {"tool": "whois", "user_id": 5},
            )

        self.assertEqual(queue._tasks["ABC123"]["status"], "failed")
        self.assertIn("invalid option", queue._tasks["ABC123"]["error"])


if __name__ == "__main__":
    unittest.main()
