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


    # ─── Owner isolation tests ───

    def test_get_status_with_matching_user_id_returns_task(self):
        queue = make_queue()
        task_id = queue.submit("nmap", "8.8.8.8", {"user_id": 7})
        status = queue.get_status(task_id, user_id=7)
        self.assertEqual(status["id"], task_id)
        self.assertEqual(status["status"], "queued")

    def test_get_status_with_wrong_user_id_returns_not_found(self):
        queue = make_queue()
        task_id = queue.submit("nmap", "8.8.8.8", {"user_id": 7})
        status = queue.get_status(task_id, user_id=8)
        self.assertEqual(status, {"error": "Tarea no encontrada"})

    def test_get_status_without_user_id_still_returns_task(self):
        queue = make_queue()
        task_id = queue.submit("nmap", "8.8.8.8", {"user_id": 7})
        status = queue.get_status(task_id)
        self.assertEqual(status["id"], task_id)

    def test_foreign_task_is_indistinguishable_from_missing(self):
        queue = make_queue()
        task_id = queue.submit("nmap", "8.8.8.8", {"user_id": 7})
        missing = queue.get_status("NONEXIST", user_id=7)
        foreign = queue.get_status(task_id, user_id=8)
        self.assertEqual(missing, foreign)
        self.assertEqual(missing, {"error": "Tarea no encontrada"})

    def test_list_tasks_with_user_id_filters_tasks(self):
        queue = make_queue()
        queue.submit("nmap", "8.8.8.8", {"user_id": 7})
        queue.submit("nmap", "8.8.8.9", {"user_id": 8})
        queue.submit("nmap", "8.8.8.10", {"user_id": 7})
        tasks = queue.list_tasks(user_id=7)
        self.assertEqual(len(tasks), 2)
        for t in tasks:
            self.assertEqual(t["params"]["user_id"], 7)

    def test_list_tasks_without_user_id_returns_all(self):
        queue = make_queue()
        queue.submit("nmap", "8.8.8.8", {"user_id": 7})
        queue.submit("nmap", "8.8.8.9", {"user_id": 8})
        tasks = queue.list_tasks()
        self.assertEqual(len(tasks), 2)

    def test_list_tasks_foreign_user_gets_empty_list(self):
        queue = make_queue()
        queue.submit("nmap", "8.8.8.8", {"user_id": 7})
        tasks = queue.list_tasks(user_id=99)
        self.assertEqual(tasks, [])


if __name__ == "__main__":
    unittest.main()
