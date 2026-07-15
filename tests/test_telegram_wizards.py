import asyncio
import inspect
import os
import re
import socket
import threading
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

import dns.resolver
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.error import BadRequest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import telegram_bot
from hacking import network as network_hacking
from hacking import web as web_hacking
from task_queue import TaskQueue


def make_text_update(text, uid=7, chat_id=70):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    user = SimpleNamespace(id=uid, username="tester", full_name="Test User")
    chat = SimpleNamespace(id=chat_id)
    return SimpleNamespace(effective_user=user, effective_chat=chat, message=message)


def make_callback_update(data, uid=7, chat_id=70):
    callback_message = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=callback_message,
    )
    user = SimpleNamespace(id=uid, username="tester", full_name="Test User")
    chat = SimpleNamespace(id=chat_id)
    return SimpleNamespace(
        effective_user=user,
        effective_chat=chat,
        callback_query=query,
    ), query


class TelegramWizardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        telegram_bot.user_wizards.clear()

    def tearDown(self):
        telegram_bot.user_wizards.clear()

    def test_new_wizard_has_scoped_metadata(self):
        with patch.object(telegram_bot.secrets, "token_hex", return_value="abc123ef"):
            wizard = telegram_bot._new_wizard(7, "recon", 70)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["session_id"], "abc123ef")
        self.assertEqual(wizard["type"], "recon")
        self.assertEqual(wizard["step"], "select_type")
        self.assertEqual(wizard["chat_id"], 70)
        self.assertGreater(wizard["created_at"], 0)
        self.assertEqual(wizard["data"], {})

    def test_wizard_expires_after_thirty_minutes(self):
        with patch.object(telegram_bot.time, "time", return_value=1000.0):
            telegram_bot._new_wizard(7, "recon", 70)

        self.assertFalse(telegram_bot._is_wizard_expired(7, now=2799.0))
        self.assertTrue(telegram_bot._is_wizard_expired(7, now=2801.0))
        self.assertNotIn(7, telegram_bot.user_wizards)

    def test_consume_requires_exact_session(self):
        wizard = telegram_bot._new_wizard(7, "web", 70)

        self.assertIsNone(telegram_bot._consume_wizard(7, "stale000"))
        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertIs(wizard, telegram_bot._consume_wizard(7, wizard["session_id"]))
        self.assertNotIn(7, telegram_bot.user_wizards)

    def test_wizard_callback_is_compact_and_scoped(self):
        wizard = telegram_bot._new_wizard(7, "payload", 70)
        data = telegram_bot._wizard_callback(wizard, "lang", "bash")

        self.assertRegex(data, r"^w:[0-9a-f]{8}:payload:lang:bash$")
        self.assertLessEqual(len(data.encode("utf-8")), 64)

    async def test_recon_start_exposes_only_scoped_scan_types(self):
        update = make_text_update("unused")

        await telegram_bot._start_recon_wizard(update, 7)

        wizard = telegram_bot.user_wizards[7]
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        choices = [
            (button.text, button.callback_data)
            for row in markup.inline_keyboard
            for button in row
            if f":{wizard['type']}:type:" in button.callback_data
        ]
        self.assertEqual(
            choices,
            [
                (
                    "⚡ Quick",
                    telegram_bot._wizard_callback(wizard, "type", "quick"),
                ),
                (
                    "🔎 Normal",
                    telegram_bot._wizard_callback(wizard, "type", "normal"),
                ),
                (
                    "🧠 Full",
                    telegram_bot._wizard_callback(wizard, "type", "full"),
                ),
            ],
        )

    async def test_recon_quick_selection_keeps_session_and_asks_for_target(self):
        wizard = telegram_bot._new_wizard(7, "recon", 70)
        envelope = {
            key: wizard[key]
            for key in ("session_id", "type", "chat_id", "created_at", "data")
        }
        data = telegram_bot._wizard_callback(wizard, "type", "quick")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(telegram_bot.user_wizards[7], wizard)
        self.assertEqual(
            {key: wizard[key] for key in envelope},
            envelope,
        )
        self.assertEqual(wizard.get("scan_type"), "quick")
        self.assertEqual(wizard["step"], "awaiting_target")
        self.assertIsNone(wizard["target"])
        prompt = query.edit_message_text.await_args.args[0].lower()
        self.assertIn("ip", prompt)
        self.assertIn("dominio", prompt)
        self.assertIn("rango", prompt)

    async def test_web_start_exposes_only_scoped_real_operations(self):
        update = make_text_update("unused")

        await telegram_bot._start_web_wizard(update, 7)

        wizard = telegram_bot.user_wizards[7]
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        choices = [
            (button.text, button.callback_data)
            for row in markup.inline_keyboard
            for button in row
            if f":{wizard['type']}:type:" in button.callback_data
        ]
        self.assertEqual(
            choices,
            [
                (
                    "🔎 Reconocimiento Web",
                    telegram_bot._wizard_callback(
                        wizard, "type", "recon"
                    ),
                ),
                (
                    "🛡️ Auditoría de Vulnerabilidades",
                    telegram_bot._wizard_callback(
                        wizard, "type", "vuln"
                    ),
                ),
            ],
        )

    async def test_web_brute_callback_is_not_allowlisted(self):
        wizard = telegram_bot._new_wizard(7, "web", 70)
        original = dict(wizard)
        data = telegram_bot._wizard_callback(
            wizard, "type", "brute"
        )
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(
                telegram_bot, "_rate_limit_msg", return_value=None
            ),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])

    async def test_web_option_selection_stores_type_and_asks_for_http_url(self):
        wizard = telegram_bot._new_wizard(7, "web", 70)
        data = telegram_bot._wizard_callback(
            wizard, "type", "vuln"
        )
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(
                telegram_bot, "_rate_limit_msg", return_value=None
            ),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["audit_type"], "vuln")
        self.assertEqual(wizard["step"], "awaiting_target")
        self.assertIsNone(wizard["target"])
        prompt = query.edit_message_text.await_args.args[0].lower()
        self.assertIn("http", prompt)
        self.assertIn("url", prompt)

    async def test_recon_valid_target_submits_nmap_and_returns_to_menu(self):
        update = make_text_update("8.8.8.8")
        update.message.reply_text.return_value = Mock(name="acknowledgement")
        wizard = telegram_bot._new_wizard(
            7,
            "recon",
            70,
            step="awaiting_target",
            scan_type="quick",
        )
        session_id = wizard["session_id"]

        def persist_after_consume(uid, target, target_type):
            self.assertNotIn(7, telegram_bot.user_wizards)

        def submit_after_consume(task_type, target, params):
            self.assertNotIn(7, telegram_bot.user_wizards)
            return "RECON-1"

        poll_request = Mock(name="poll_request")
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.target_engine,
                "set_target",
                side_effect=persist_after_consume,
            ) as set_target,
            patch.object(
                telegram_bot.task_queue,
                "submit",
                side_effect=submit_after_consume,
            ) as submit,
            patch.object(
                telegram_bot,
                "_consume_wizard",
                wraps=telegram_bot._consume_wizard,
            ) as consume,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(
                telegram_bot,
                "_poll_nmap_task",
                new=Mock(return_value=poll_request),
            ) as poll,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertNotIn(7, telegram_bot.user_wizards)
        consume.assert_called_once_with(7, session_id)
        set_target.assert_called_once_with(7, "8.8.8.8", "ip")
        submit.assert_called_once_with(
            "nmap",
            "8.8.8.8",
            {"scan_type": "quick", "user_id": 7},
        )
        self.assertEqual(audit.call_args.args[2:5], ("wizard:recon", "8.8.8.8", "ok"))
        acknowledgement = update.message.reply_text.return_value
        poll.assert_called_once_with(
            acknowledgement,
            "RECON-1",
            return_to_menu=True,
        )
        create_task.assert_called_once_with(poll_request)

    async def test_recon_invalid_target_keeps_retryable_session(self):
        update = make_text_update("8.8.8.8")
        wizard = telegram_bot._new_wizard(
            7,
            "recon",
            70,
            step="awaiting_target",
            scan_type="quick",
        )
        original = dict(wizard)
        validate_target = Mock(return_value="target rejected")
        tools_engine = SimpleNamespace(validate_target=validate_target)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.dict(telegram_bot.__dict__, {"tools_engine": tools_engine}),
            patch.object(telegram_bot.target_engine, "set_target") as set_target,
            patch.object(telegram_bot.task_queue, "submit") as submit,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.handle_text(update, None)

        validate_target.assert_called_once_with("8.8.8.8")
        self.assertIs(telegram_bot.user_wizards[7], wizard)
        self.assertEqual(wizard, original)
        self.assertEqual(wizard["step"], "awaiting_target")
        set_target.assert_not_called()
        submit.assert_not_called()
        audit.assert_not_called()
        create_task.assert_not_called()
        self.assertIn(
            "target rejected",
            update.message.reply_text.await_args.args[0],
        )

    async def test_recon_derives_network_and_domain_target_types(self):
        for target, expected_type in (
            ("8.8.8.0/24", "network"),
            ("example.com", "domain"),
        ):
            with self.subTest(target=target):
                telegram_bot.user_wizards.clear()
                update = make_text_update(target)
                telegram_bot._new_wizard(
                    7,
                    "recon",
                    70,
                    step="awaiting_target",
                    scan_type="normal",
                )

                with (
                    patch.object(
                        telegram_bot,
                        "_check_role",
                        return_value=True,
                    ),
                    patch.object(
                        telegram_bot,
                        "_rate_limit_msg",
                        return_value=None,
                    ),
                    patch.object(
                        telegram_bot.target_engine,
                        "set_target",
                    ) as set_target,
                    patch.object(
                        telegram_bot.task_queue,
                        "submit",
                        return_value="RECON-1",
                    ),
                    patch.object(telegram_bot.audit_log, "log"),
                    patch.object(
                        telegram_bot,
                        "_poll_nmap_task",
                        new=Mock(return_value=None),
                    ),
                    patch.object(asyncio, "create_task"),
                ):
                    await telegram_bot.handle_text(update, None)

                set_target.assert_called_once_with(
                    7,
                    target,
                    expected_type,
                )

    def test_hash_validation_uses_real_hash_id_list_contract(self):
        algorithm, error = telegram_bot._validate_hash_algorithm(
            "5d41402abc4b2a76b9719d911017c592"
        )

        self.assertEqual(algorithm, "MD5")
        self.assertIsNone(error)

    def test_hash_validation_rejects_identified_but_unimplemented_algorithm(self):
        bcrypt = "$2b12$" + "a" * 53
        algorithm, error = telegram_bot._validate_hash_algorithm(bcrypt)

        self.assertIsNone(algorithm)
        self.assertIn("no soportado", error.lower())

    def test_hash_validation_rejects_unknown_input(self):
        algorithm, error = telegram_bot._validate_hash_algorithm("archive.zip")

        self.assertIsNone(algorithm)
        self.assertTrue(error)

    def test_web_normalization_accepts_valid_targets(self):
        cases = {
            "example.com/login?q=1": ("https://example.com/login?q=1", "example.com"),
            "HTTP://example.com:8080/a": ("http://example.com:8080/a", "example.com"),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                normalized, hostname, error = telegram_bot._normalize_web_input(raw)
                self.assertIsNone(error)
                self.assertEqual((normalized, hostname), expected)

    def test_web_normalization_accepts_scheme_less_host_with_port(self):
        normalized, hostname, error = telegram_bot._normalize_web_input(
            "example.com:8080/a"
        )

        self.assertIsNone(error)
        self.assertEqual(normalized, "https://example.com:8080/a")
        self.assertEqual(hostname, "example.com")

    def test_web_normalization_rejects_malformed_or_private_targets(self):
        values = [
            "",
            "https://",
            "not a url",
            "ftp://example.com",
            "https://[::1",
            "https://example.com:abc",
            "http://127.0.0.1",
            "http://10.0.0.1",
            "https://example .com",
            "https://" + "a" * 2049,
        ]
        for raw in values:
            with self.subTest(raw=raw):
                normalized, hostname, error = telegram_bot._normalize_web_input(raw)
                self.assertIsNone(normalized)
                self.assertIsNone(hostname)
                self.assertTrue(error)

    def test_web_normalization_rejects_del_and_c1_controls(self):
        for codepoint in (0x7F, 0x80, 0x9F):
            with self.subTest(codepoint=codepoint):
                raw = f"https://example.com/a{chr(codepoint)}b"
                normalized, hostname, error = telegram_bot._normalize_web_input(raw)
                self.assertIsNone(normalized)
                self.assertIsNone(hostname)
                self.assertTrue(error)

    def test_web_normalization_still_rejects_non_http_scheme_without_slashes(self):
        normalized, hostname, error = telegram_bot._normalize_web_input(
            "mailto:user@example.com"
        )

        self.assertIsNone(normalized)
        self.assertIsNone(hostname)
        self.assertTrue(error)

    def test_web_normalization_rejects_browser_parser_differentials(self):
        values = [
            "http://10.0.0.1\\@example.com/",
            "https://user@example.com/",
            "https://user:secret@example.com/",
        ]

        for raw in values:
            with self.subTest(raw=raw):
                normalized, hostname, error = telegram_bot._normalize_web_input(
                    raw
                )
                self.assertIsNone(normalized)
                self.assertIsNone(hostname)
                self.assertTrue(error)

    async def test_web_parser_differential_is_rejected_before_persistence(self):
        update = make_text_update("http://10.0.0.1\\@example.com/")
        wizard = telegram_bot._new_wizard(
            7, "web", 70, step="awaiting_target", audit_type="vuln"
        )
        original = dict(wizard)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine") as target_engine,
            patch.object(telegram_bot, "task_queue") as task_queue,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        target_engine.set_target.assert_not_called()
        task_queue.submit.assert_not_called()

    async def test_invalid_web_input_keeps_step_and_has_no_side_effects(self):
        update = make_text_update("https://[")
        wizard = telegram_bot._new_wizard(
            7, "web", 70, step="awaiting_target", audit_type="vuln"
        )
        original = dict(wizard)
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine") as target_engine,
            patch.object(telegram_bot, "task_queue") as task_queue,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        target_engine.set_target.assert_not_called()
        task_queue.submit.assert_not_called()
        audit.assert_not_called()
        create_task.assert_not_called()
        retry = update.message.reply_text.await_args.args[0].lower()
        self.assertIn("http(s)", retry)
        self.assertIn("intenta de nuevo", retry)

    async def test_cross_chat_web_target_leaves_session_unchanged(self):
        update = make_text_update("example.com", chat_id=71)
        wizard = telegram_bot._new_wizard(
            7, "web", 70, step="awaiting_target", audit_type="vuln"
        )
        original = dict(wizard)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine") as target_engine,
            patch.object(telegram_bot, "task_queue") as task_queue,
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards.get(7))
        self.assertEqual(wizard, original)
        self.assertEqual(target_engine.method_calls, [])
        self.assertEqual(task_queue.method_calls, [])
        audit.assert_not_called()

    async def test_expired_cross_chat_session_expires_before_ownership_check(self):
        update = make_text_update("🔑 Crack", chat_id=71)
        wizard = telegram_bot._new_wizard(
            7, "web", 70, step="awaiting_target", audit_type="vuln"
        )
        wizard["created_at"] -= telegram_bot.WIZARD_TTL_SECONDS + 1

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot, "_start_crack_wizard", new=AsyncMock()
            ) as start_crack,
            patch.object(
                telegram_bot, "_chat_api", new=AsyncMock()
            ) as chat_api,
            patch.object(telegram_bot, "target_engine") as target_engine,
            patch.object(telegram_bot, "task_queue") as task_queue,
            patch.object(
                telegram_bot.hacking.crypto, "hash_crack"
            ) as hash_crack,
            patch.object(
                telegram_bot.hacking.payloads, "reverse_shell"
            ) as reverse_shell,
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertNotIn(7, telegram_bot.user_wizards)
        start_crack.assert_not_awaited()
        chat_api.assert_not_awaited()
        self.assertEqual(target_engine.method_calls, [])
        self.assertEqual(task_queue.method_calls, [])
        hash_crack.assert_not_called()
        reverse_shell.assert_not_called()
        audit.assert_not_called()
        reply = update.message.reply_text.await_args.args[0].lower()
        self.assertIn("expiro", reply)
        self.assertNotIn("otro chat", reply)

    async def test_cross_chat_custom_crack_leaves_session_unchanged(self):
        update = make_text_update("hello, secret", chat_id=71)
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="awaiting_dictionary",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )
        original = dict(wizard)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine") as target_engine,
            patch.object(telegram_bot, "task_queue") as task_queue,
            patch.object(
                telegram_bot.hacking.crypto, "hash_crack"
            ) as hash_crack,
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards.get(7))
        self.assertEqual(wizard, original)
        self.assertEqual(target_engine.method_calls, [])
        self.assertEqual(task_queue.method_calls, [])
        hash_crack.assert_not_called()
        audit.assert_not_called()

    async def test_cross_chat_reverse_shell_endpoint_leaves_session_unchanged(self):
        update = make_text_update("192.168.1.20:4444", chat_id=71)
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="awaiting_endpoint",
            payload_type="reverse",
            lang="bash",
        )
        original = dict(wizard)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine") as target_engine,
            patch.object(telegram_bot, "task_queue") as task_queue,
            patch.object(
                telegram_bot.hacking.payloads, "reverse_shell"
            ) as reverse_shell,
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards.get(7))
        self.assertEqual(wizard, original)
        self.assertEqual(target_engine.method_calls, [])
        self.assertEqual(task_queue.method_calls, [])
        reverse_shell.assert_not_called()
        audit.assert_not_called()

    async def test_recon_delivery_failure_keeps_single_success_audit(self):
        update = make_text_update("8.8.8.8")
        update.message.reply_text.side_effect = RuntimeError("delivery failed")
        telegram_bot._new_wizard(
            7,
            "recon",
            70,
            step="awaiting_target",
            scan_type="normal",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine"),
            patch.object(
                telegram_bot.task_queue,
                "submit",
                return_value="RECON-1",
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(asyncio, "create_task") as create_task,
        ):
            with self.assertRaisesRegex(RuntimeError, "delivery failed"):
                await telegram_bot.handle_text(update, None)

        self.assertEqual(
            [call.args[4] for call in audit.call_args_list], ["ok"]
        )
        create_task.assert_not_called()

    async def test_recon_task_failure_has_single_error_audit(self):
        update = make_text_update("8.8.8.8")
        telegram_bot._new_wizard(
            7,
            "recon",
            70,
            step="awaiting_target",
            scan_type="normal",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine"),
            patch.object(
                telegram_bot.task_queue,
                "submit",
                side_effect=RuntimeError("submit failed"),
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertEqual(
            [call.args[4] for call in audit.call_args_list], ["error"]
        )

    async def test_valid_web_recon_submits_canonical_url_and_polls(self):
        update = make_text_update("example.com:8080/a")
        acknowledgement = Mock(name="acknowledgement")
        update.message.reply_text.return_value = acknowledgement
        wizard = telegram_bot._new_wizard(
            7,
            "web",
            70,
            step="awaiting_target",
            audit_type="recon",
        )
        session_id = wizard["session_id"]

        def persist_after_consume(uid, target, target_type):
            self.assertNotIn(7, telegram_bot.user_wizards)

        def submit_after_consume(task_type, target, params):
            self.assertNotIn(7, telegram_bot.user_wizards)
            return "WEB-RECON-1"

        poll_request = Mock(name="poll_request")
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(
                telegram_bot, "_rate_limit_msg", return_value=None
            ),
            patch.object(
                telegram_bot.target_engine,
                "set_target",
                side_effect=persist_after_consume,
            ) as set_target,
            patch.object(
                telegram_bot.task_queue,
                "submit",
                side_effect=submit_after_consume,
            ) as submit,
            patch.object(
                telegram_bot,
                "_consume_wizard",
                wraps=telegram_bot._consume_wizard,
            ) as consume,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(
                telegram_bot,
                "_poll_playbook_task",
                new=Mock(return_value=poll_request),
                create=True,
            ) as poll,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertNotIn(7, telegram_bot.user_wizards)
        consume.assert_called_once_with(7, session_id)
        set_target.assert_called_once_with(
            7, "https://example.com:8080/a", "url"
        )
        submit.assert_called_once_with(
            "playbook",
            "https://example.com:8080/a",
            {"playbook": "recon_web", "depth": "normal", "user_id": 7},
        )
        self.assertEqual(
            audit.call_args.args[2:5],
            ("wizard:web", "https://example.com:8080/a", "ok"),
        )
        self.assertIn("WEB-RECON-1", update.message.reply_text.await_args.args[0])
        poll.assert_called_once_with(
            acknowledgement,
            "WEB-RECON-1",
            "Reconocimiento Web",
            return_to_menu=True,
        )
        create_task.assert_called_once_with(poll_request)

    async def test_valid_web_audit_submits_normalized_url_at_deep_depth(self):
        update = make_text_update("example.com:8080/a")
        acknowledgement = Mock(name="acknowledgement")
        update.message.reply_text.return_value = acknowledgement
        telegram_bot._new_wizard(
            7,
            "web",
            70,
            step="awaiting_target",
            audit_type="vuln",
        )
        poll_request = Mock(name="poll_request")
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(
                telegram_bot, "_rate_limit_msg", return_value=None
            ),
            patch.object(
                telegram_bot.target_engine, "set_target"
            ) as set_target,
            patch.object(
                telegram_bot.task_queue,
                "submit",
                return_value="WEB-VULN-1",
            ) as submit,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(
                telegram_bot,
                "_poll_playbook_task",
                new=Mock(return_value=poll_request),
                create=True,
            ) as poll,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertNotIn(7, telegram_bot.user_wizards)
        set_target.assert_called_once_with(
            7, "https://example.com:8080/a", "url"
        )
        submit.assert_called_once_with(
            "playbook",
            "https://example.com:8080/a",
            {"playbook": "web_audit", "depth": "profundo", "user_id": 7},
        )
        self.assertEqual(
            audit.call_args.args[2:5],
            ("wizard:web", "https://example.com:8080/a", "ok"),
        )
        poll.assert_called_once_with(
            acknowledgement,
            "WEB-VULN-1",
            "Auditoría de Vulnerabilidades",
            return_to_menu=True,
        )
        create_task.assert_called_once_with(poll_request)

    def test_actual_reverse_shell_result_is_formattable(self):
        result = telegram_bot.hacking.payloads.reverse_shell(
            "8.8.8.8", 4444, "bash"
        )

        message = telegram_bot._format_payload(result)

        self.assertIn(result["decoded"], message)
        self.assertIn(result["encoded"], message)
        self.assertIn("bash", message.lower())

    async def test_payload_menu_exposes_only_reverse_and_webshell(self):
        update = make_text_update("unused")

        await telegram_bot._start_payload_wizard(update, 7)

        wizard = telegram_bot.user_wizards[7]
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        choices = [
            (button.text, button.callback_data)
            for row in markup.inline_keyboard
            for button in row
            if f":{wizard['type']}:type:" in button.callback_data
        ]
        self.assertEqual(
            choices,
            [
                (
                    "🐚 Reverse Shell",
                    telegram_bot._wizard_callback(
                        wizard, "type", "reverse"
                    ),
                ),
                (
                    "💻 Webshell",
                    telegram_bot._wizard_callback(
                        wizard, "type", "webshell"
                    ),
                ),
            ],
        )

    async def test_reverse_language_menu_exposes_only_bash(self):
        wizard = telegram_bot._new_wizard(7, "payload", 70)
        _, query = make_callback_update("unused")

        await telegram_bot._handle_payload_type(
            query, 7, wizard, "reverse"
        )

        markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        choices = [
            (button.text, button.callback_data)
            for row in markup.inline_keyboard
            for button in row
            if f":{wizard['type']}:lang:" in button.callback_data
        ]
        self.assertEqual(
            choices,
            [
                (
                    "🔹 Bash",
                    telegram_bot._wizard_callback(
                        wizard, "lang", "bash"
                    ),
                ),
            ],
        )

    async def test_webshell_language_menu_exposes_only_php(self):
        wizard = telegram_bot._new_wizard(7, "payload", 70)
        _, query = make_callback_update("unused")

        await telegram_bot._handle_payload_type(
            query, 7, wizard, "webshell"
        )

        markup = query.edit_message_text.await_args.kwargs["reply_markup"]
        choices = [
            (button.text, button.callback_data)
            for row in markup.inline_keyboard
            for button in row
            if f":{wizard['type']}:lang:" in button.callback_data
        ]
        self.assertEqual(
            choices,
            [
                (
                    "🟨 PHP",
                    telegram_bot._wizard_callback(
                        wizard, "lang", "php"
                    ),
                ),
            ],
        )

    async def test_forged_removed_reverse_language_is_rejected_before_mutation(self):
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="select_lang",
            payload_type="reverse",
        )
        original = dict(wizard)
        data = telegram_bot._wizard_callback(wizard, "lang", "python")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.payloads, "reverse_shell"
            ) as reverse_shell,
            patch.object(
                telegram_bot.hacking.payloads, "webshell"
            ) as webshell,
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        reverse_shell.assert_not_called()
        webshell.assert_not_called()
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])

    async def test_forged_removed_webshell_language_is_rejected_before_generator(self):
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="select_lang",
            payload_type="webshell",
        )
        original = dict(wizard)
        data = telegram_bot._wizard_callback(wizard, "lang", "asp")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.payloads, "reverse_shell"
            ) as reverse_shell,
            patch.object(
                telegram_bot.hacking.payloads,
                "webshell",
                return_value={
                    "language": "asp",
                    "decoded": "removed",
                    "encoded": "removed",
                },
            ) as webshell,
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards.get(7))
        self.assertEqual(wizard, original)
        reverse_shell.assert_not_called()
        webshell.assert_not_called()
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])

    async def test_forged_meterpreter_callback_is_rejected(self):
        wizard = telegram_bot._new_wizard(7, "payload", 70)
        original = dict(wizard)
        data = telegram_bot._wizard_callback(wizard, "type", "meterp")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])

    async def test_reverse_language_prompts_once_for_endpoint(self):
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="select_lang",
            payload_type="reverse",
        )
        data = telegram_bot._wizard_callback(wizard, "lang", "bash")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "awaiting_endpoint")
        self.assertEqual(wizard["lang"], "bash")
        query.answer.assert_awaited_once_with()
        query.edit_message_text.assert_awaited_once()
        prompt = query.edit_message_text.await_args.args[0].lower()
        self.assertIn("ip:puerto", prompt)

    def test_payload_endpoint_parser_accepts_private_ipv4_and_bracketed_ipv6(self):
        parser = getattr(telegram_bot, "_parse_payload_endpoint", None)
        self.assertIsNotNone(parser, "payload endpoint parser is missing")

        self.assertEqual(
            parser("192.168.1.20:4444"),
            ("192.168.1.20", 4444, None),
        )
        self.assertEqual(
            parser("[2001:db8::20]:65535"),
            ("2001:db8::20", 65535, None),
        )

    def test_payload_endpoint_parser_rejects_unsafe_or_malformed_values(self):
        parser = getattr(telegram_bot, "_parse_payload_endpoint", None)
        self.assertIsNotNone(parser, "payload endpoint parser is missing")

        for value in (
            "192.168.1.20",
            "not-an-ip:4444",
            "2001:db8::20:4444",
            "0.0.0.0:4444",
            "224.0.0.1:4444",
            "[::]:4444",
            "[ff02::1]:4444",
            "192.168.1.20:0",
            "192.168.1.20:65536",
        ):
            with self.subTest(value=value):
                ip, port, error = parser(value)
                self.assertIsNone(ip)
                self.assertIsNone(port)
                self.assertTrue(error)

    def test_payload_endpoint_parser_enforces_address_and_port_grammar(self):
        parser = telegram_bot._parse_payload_endpoint

        self.assertEqual(
            parser("[2001:db8::20]:4444"),
            ("2001:db8::20", 4444, None),
        )
        for value in (
            "[192.168.1.20]:4444",
            "192.168.1.20:+4444",
            "192.168.1.20: 4444",
            "192.168.1.20:4444 ",
            "192.168.1.20:٤٤٤٤",
        ):
            with self.subTest(value=value):
                ip, port, error = parser(value)
                self.assertIsNone(ip)
                self.assertIsNone(port)
                self.assertTrue(error)

    async def test_valid_reverse_endpoint_consumes_then_generates_and_returns_to_menu(self):
        update = make_text_update("192.168.1.20:4444")
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="awaiting_endpoint",
            payload_type="reverse",
            lang="bash",
        )
        result = {
            "type": "bash",
            "decoded": "real payload",
            "encoded": "real-b64",
            "listener": "nc -lvnp 4444",
        }

        def generate_after_consume(ip, port, lang):
            self.assertNotIn(7, telegram_bot.user_wizards)
            return result

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.payloads,
                "reverse_shell",
                side_effect=generate_after_consume,
            ) as reverse_shell,
            patch.object(telegram_bot.audit_log, "log"),
            patch.object(
                telegram_bot, "_chat_api", new=AsyncMock()
            ) as chat_api,
        ):
            await telegram_bot.handle_text(update, None)

        reverse_shell.assert_called_once_with(
            "192.168.1.20", 4444, "bash"
        )
        self.assertNotIn(7, telegram_bot.user_wizards)
        chat_api.assert_not_awaited()
        first, menu = update.message.reply_text.await_args_list
        self.assertIn("real payload", first.args[0])
        self.assertIn("real-b64", first.args[0])
        self.assertIn("nc -lvnp 4444", first.args[0])
        self.assertEqual(menu.args[0], "Menú principal:")
        self.assertIs(
            menu.kwargs["reply_markup"], telegram_bot.MAIN_KEYBOARD
        )

    async def test_invalid_reverse_endpoint_remains_retryable(self):
        update = make_text_update("0.0.0.0:4444")
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="awaiting_endpoint",
            payload_type="reverse",
            lang="bash",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.payloads, "reverse_shell"
            ) as reverse_shell,
            patch.object(
                telegram_bot, "_chat_api", new=AsyncMock()
            ) as chat_api,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "awaiting_endpoint")
        reverse_shell.assert_not_called()
        chat_api.assert_not_awaited()
        self.assertIn(
            "inválido", update.message.reply_text.await_args.args[0].lower()
        )

    async def test_reverse_endpoint_trailing_whitespace_remains_retryable(self):
        update = make_text_update("192.168.1.20:4444 ")
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="awaiting_endpoint",
            payload_type="reverse",
            lang="bash",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.payloads, "reverse_shell"
            ) as reverse_shell,
            patch.object(
                telegram_bot, "_chat_api", new=AsyncMock()
            ) as chat_api,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards.get(7))
        self.assertEqual(wizard["step"], "awaiting_endpoint")
        reverse_shell.assert_not_called()
        chat_api.assert_not_awaited()

    async def test_reverse_shell_delivery_failure_has_one_audit_status(self):
        update = make_text_update("192.168.1.20:4444")
        update.message.reply_text.side_effect = RuntimeError("delivery failed")
        telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="awaiting_endpoint",
            payload_type="reverse",
            lang="bash",
        )
        result = {"type": "bash", "decoded": "payload", "encoded": "b64"}

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.payloads,
                "reverse_shell",
                return_value=result,
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(telegram_bot, "_chat_api", new=AsyncMock()),
        ):
            with self.assertRaisesRegex(RuntimeError, "delivery failed"):
                await telegram_bot.handle_text(update, None)

        self.assertEqual(
            [call.args[4] for call in audit.call_args_list], ["ok"]
        )

    async def test_reverse_shell_tool_failure_has_single_error_audit(self):
        update = make_text_update("192.168.1.20:4444")
        telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="awaiting_endpoint",
            payload_type="reverse",
            lang="bash",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.payloads,
                "reverse_shell",
                side_effect=RuntimeError("tool failed"),
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(telegram_bot, "_chat_api", new=AsyncMock()),
        ):
            await telegram_bot.handle_text(update, None)

        self.assertEqual(
            [call.args[4] for call in audit.call_args_list], ["error"]
        )

    async def test_webshell_executes_after_language_without_ip_prompt(self):
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="select_lang",
            payload_type="webshell",
        )
        data = telegram_bot._wizard_callback(wizard, "lang", "php")
        _, query = make_callback_update(data)
        result = {"language": "php", "decoded": "<?php ?>", "encoded": "b64"}

        with (
            patch.object(
                telegram_bot.hacking.payloads,
                "webshell",
                return_value=result,
            ) as webshell,
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot._handle_payload_lang(
                query, 7, wizard, "php"
            )

        webshell.assert_called_once_with("php")
        self.assertNotIn(7, telegram_bot.user_wizards)
        self.assertIn("Webshell", query.edit_message_text.await_args.args[0])
        query.message.reply_text.assert_awaited_once_with(
            "Menú principal:", reply_markup=telegram_bot.MAIN_KEYBOARD
        )

    async def test_webshell_callback_consumes_before_answer_then_runs_tool(self):
        wizard = telegram_bot._new_wizard(
            7,
            "payload",
            70,
            step="select_lang",
            payload_type="webshell",
        )
        data = telegram_bot._wizard_callback(wizard, "lang", "php")
        update, query = make_callback_update(data)
        events = []

        async def answer_after_consume(*args, **kwargs):
            self.assertNotIn(7, telegram_bot.user_wizards)
            events.append("answer")

        def webshell_after_answer(lang):
            self.assertEqual(events, ["answer"])
            events.append("tool")
            return {
                "language": lang,
                "decoded": "<?php ?>",
                "encoded": "b64",
            }

        query.answer.side_effect = answer_after_consume
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.payloads,
                "webshell",
                side_effect=webshell_after_answer,
            ) as webshell,
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertEqual(events, ["answer", "tool"])
        query.answer.assert_awaited_once_with()
        webshell.assert_called_once_with("php")
        self.assertNotIn(7, telegram_bot.user_wizards)

    async def test_back_sends_reply_keyboard_as_new_message(self):
        wizard = telegram_bot._new_wizard(
            7, "web", 70, step="awaiting_target"
        )
        data = telegram_bot._wizard_callback(wizard, "back", "main")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)

        edit_markup = query.edit_message_text.await_args.kwargs.get("reply_markup")
        self.assertNotIsInstance(edit_markup, ReplyKeyboardMarkup)
        query.message.reply_text.assert_awaited_once_with(
            "Menú principal:", reply_markup=telegram_bot.MAIN_KEYBOARD
        )

    async def test_web_depth_callback_is_rejected_without_execution(self):
        wizard = telegram_bot._new_wizard(
            7,
            "web",
            70,
            step="awaiting_depth",
            target="https://example.com",
            audit_type="vuln",
        )
        original = dict(wizard)
        data = telegram_bot._wizard_callback(wizard, "depth", "normal")
        update, query = make_callback_update(data)
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.task_queue, "submit") as submit,
            patch.object(
                telegram_bot.target_engine, "set_target"
            ) as set_target,
        ):
            await telegram_bot.handle_callback(update, None)

        submit.assert_not_called()
        set_target.assert_not_called()
        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])
        self.assertIn("expir", query.answer.await_args.args[0].lower())

    async def test_old_recon_callback_cannot_mutate_new_recon_session(self):
        old = telegram_bot._new_wizard(7, "recon", 70)
        old_data = telegram_bot._wizard_callback(old, "type", "quick")
        current = telegram_bot._new_wizard(7, "recon", 70)
        original = dict(current)
        update, query = make_callback_update(old_data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.log, "warning") as warning,
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(current, telegram_bot.user_wizards[7])
        self.assertEqual(current, original)
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])
        self.assertEqual(warning.call_args.args[1], "session_mismatch")

    async def test_expired_callback_removes_only_expired_session(self):
        wizard = telegram_bot._new_wizard(7, "recon", 70)
        wizard["created_at"] -= telegram_bot.WIZARD_TTL_SECONDS + 1
        data = telegram_bot._wizard_callback(wizard, "type", "quick")
        update, query = make_callback_update(data)
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)
        self.assertNotIn(7, telegram_bot.user_wizards)
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])
        self.assertIn("expir", query.answer.await_args.args[0].lower())

    async def test_old_back_and_cancel_leave_new_session_untouched(self):
        old = telegram_bot._new_wizard(7, "recon", 70)
        callbacks = [
            telegram_bot._wizard_callback(old, "back", "main"),
            telegram_bot._wizard_callback(old, "cancel", "now"),
        ]
        for data in callbacks:
            with self.subTest(data=data):
                current = telegram_bot._new_wizard(7, "osint", 70)
                update, query = make_callback_update(data)
                with (
                    patch.object(telegram_bot, "_check_role", return_value=True),
                    patch.object(
                        telegram_bot, "_rate_limit_msg", return_value=None
                    ),
                ):
                    await telegram_bot.handle_callback(update, None)
                self.assertIs(current, telegram_bot.user_wizards[7])
                query.edit_message_text.assert_not_awaited()
                query.answer.assert_awaited_once()
                self.assertTrue(query.answer.await_args.kwargs["show_alert"])
                self.assertIn("expir", query.answer.await_args.args[0].lower())

    async def test_cross_user_and_cross_chat_callbacks_are_rejected(self):
        wizard = telegram_bot._new_wizard(7, "recon", 70)
        data = telegram_bot._wizard_callback(wizard, "type", "quick")
        for uid, chat_id in ((8, 70), (7, 71)):
            with self.subTest(uid=uid, chat_id=chat_id):
                update, query = make_callback_update(
                    data, uid=uid, chat_id=chat_id
                )
                with (
                    patch.object(telegram_bot, "_check_role", return_value=True),
                    patch.object(
                        telegram_bot, "_rate_limit_msg", return_value=None
                    ),
                ):
                    await telegram_bot.handle_callback(update, None)
                query.edit_message_text.assert_not_awaited()
                query.answer.assert_awaited_once()
                self.assertTrue(query.answer.await_args.kwargs["show_alert"])
                self.assertIn("expir", query.answer.await_args.args[0].lower())
        self.assertIs(wizard, telegram_bot.user_wizards[7])

    async def test_foreign_user_cannot_edit_shared_message_or_block_owner(self):
        wizard = telegram_bot._new_wizard(7, "recon", 70)
        data = telegram_bot._wizard_callback(wizard, "type", "quick")
        foreign_wizard = telegram_bot._new_wizard(8, "web", 70)
        foreign_original = dict(foreign_wizard)
        foreign_update, foreign_query = make_callback_update(data, uid=8)
        owner_update, owner_query = make_callback_update(data, uid=7)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(foreign_update, None)
            self.assertIs(wizard, telegram_bot.user_wizards[7])
            self.assertIs(foreign_wizard, telegram_bot.user_wizards[8])
            self.assertEqual(foreign_wizard, foreign_original)
            foreign_query.edit_message_text.assert_not_awaited()
            foreign_query.answer.assert_awaited_once()
            self.assertTrue(
                foreign_query.answer.await_args.kwargs["show_alert"]
            )

            await telegram_bot.handle_callback(owner_update, None)

        owner_query.answer.assert_awaited_once_with()
        owner_query.edit_message_text.assert_awaited_once_with(
            "Introduce la IP, dominio o rango:"
        )
        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "awaiting_target")

    async def test_unauthorized_and_rate_limited_callbacks_alert_without_editing(self):
        for reason, role_allowed, rate_error in (
            ("unauthorized", False, None),
            ("rate_limited", True, "Espera antes de continuar."),
        ):
            with self.subTest(reason=reason):
                telegram_bot.user_wizards.clear()
                wizard = telegram_bot._new_wizard(7, "recon", 70)
                original = dict(wizard)
                data = telegram_bot._wizard_callback(
                    wizard, "type", "quick"
                )
                update, query = make_callback_update(data)

                with (
                    patch.object(
                        telegram_bot,
                        "_check_role",
                        return_value=role_allowed,
                    ),
                    patch.object(
                        telegram_bot,
                        "_rate_limit_msg",
                        return_value=rate_error,
                    ),
                    patch.object(telegram_bot.log, "warning") as warning,
                ):
                    await telegram_bot.handle_callback(update, None)

                self.assertIs(wizard, telegram_bot.user_wizards[7])
                self.assertEqual(wizard, original)
                query.edit_message_text.assert_not_awaited()
                query.answer.assert_awaited_once()
                self.assertTrue(query.answer.await_args.kwargs["show_alert"])
                self.assertEqual(warning.call_args.args[1], reason)

    async def test_malformed_and_no_session_callbacks_are_logged_and_alerted(self):
        for reason, data in (
            ("malformed_data", "not-a-scoped-callback"),
            ("no_session", "w:deadbeef:recon:type:dominio"),
        ):
            with self.subTest(reason=reason):
                telegram_bot.user_wizards.clear()
                update, query = make_callback_update(data)

                with (
                    patch.object(telegram_bot, "_check_role", return_value=True),
                    patch.object(
                        telegram_bot, "_rate_limit_msg", return_value=None
                    ),
                    patch.object(telegram_bot.log, "warning") as warning,
                ):
                    await telegram_bot.handle_callback(update, None)

                query.edit_message_text.assert_not_awaited()
                query.answer.assert_awaited_once()
                self.assertTrue(query.answer.await_args.kwargs["show_alert"])
                self.assertEqual(warning.call_args.args[1], reason)

    async def test_red_menu_exposes_only_nmap_profiles(self):
        update = make_text_update("unused")

        await telegram_bot._start_red_wizard(update, 7)

        wizard = telegram_bot.user_wizards[7]
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        choices = [
            (button.text, button.callback_data)
            for row in markup.inline_keyboard
            for button in row
            if f":{wizard['type']}:type:" in button.callback_data
        ]
        self.assertEqual(
            choices,
            [
                (
                    "⚡ Quick",
                    telegram_bot._wizard_callback(
                        wizard, "type", "quick"
                    ),
                ),
                (
                    "🔎 Normal",
                    telegram_bot._wizard_callback(
                        wizard, "type", "normal"
                    ),
                ),
                (
                    "🧠 Full",
                    telegram_bot._wizard_callback(
                        wizard, "type", "full"
                    ),
                ),
            ],
        )
        rendered = " ".join(
            button.text for row in markup.inline_keyboard for button in row
        ).lower()
        self.assertNotIn("wifi", rendered)

    async def test_forged_red_wifi_callbacks_are_rejected(self):
        for value in ("scan_wifi", "crack_wifi", "scan_lan"):
            with self.subTest(value=value):
                wizard = telegram_bot._new_wizard(7, "red", 70)
                original = dict(wizard)
                data = telegram_bot._wizard_callback(
                    wizard, "type", value
                )
                update, query = make_callback_update(data)

                with (
                    patch.object(
                        telegram_bot, "_check_role", return_value=True
                    ),
                    patch.object(
                        telegram_bot,
                        "_rate_limit_msg",
                        return_value=None,
                    ),
                ):
                    await telegram_bot.handle_callback(update, None)

                self.assertIs(wizard, telegram_bot.user_wizards[7])
                self.assertEqual(wizard, original)
                query.edit_message_text.assert_not_awaited()
                query.answer.assert_awaited_once()
                self.assertTrue(
                    query.answer.await_args.kwargs["show_alert"]
                )

    async def test_red_profile_selection_asks_for_authorized_target(self):
        wizard = telegram_bot._new_wizard(7, "red", 70)
        data = telegram_bot._wizard_callback(wizard, "type", "quick")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "awaiting_target")
        self.assertEqual(wizard["scan_type"], "quick")
        prompt = query.edit_message_text.await_args.args[0].lower()
        self.assertIn("autorizado", prompt)
        self.assertIn("ip", prompt)
        self.assertIn("dominio", prompt)
        self.assertIn("rango", prompt)

    async def test_red_valid_target_consumes_persists_submits_and_polls(self):
        update = make_text_update("8.8.8.8")
        acknowledgement = Mock(name="acknowledgement")
        update.message.reply_text.return_value = acknowledgement
        telegram_bot._new_wizard(
            7,
            "red",
            70,
            step="awaiting_target",
            scan_type="full",
        )

        def persist_after_consume(uid, target, target_type):
            self.assertNotIn(7, telegram_bot.user_wizards)

        def submit_after_consume(task_type, target, params):
            self.assertNotIn(7, telegram_bot.user_wizards)
            return "RED-1"

        poll_request = Mock(name="poll_request")
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.target_engine,
                "set_target",
                side_effect=persist_after_consume,
            ) as set_target,
            patch.object(
                telegram_bot.task_queue,
                "submit",
                side_effect=submit_after_consume,
            ) as submit,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(
                telegram_bot,
                "_poll_nmap_task",
                new=Mock(return_value=poll_request),
            ) as poll,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertNotIn(7, telegram_bot.user_wizards)
        set_target.assert_called_once_with(7, "8.8.8.8", "ip")
        submit.assert_called_once_with(
            "nmap",
            "8.8.8.8",
            {"scan_type": "full", "user_id": 7},
        )
        self.assertEqual(
            audit.call_args.args[2:5],
            ("wizard:red", "8.8.8.8", "ok"),
        )
        poll.assert_called_once_with(
            acknowledgement, "RED-1", return_to_menu=True
        )
        create_task.assert_called_once_with(poll_request)

    async def test_red_invalid_target_remains_retryable(self):
        update = make_text_update("192.168.1.0/24")
        wizard = telegram_bot._new_wizard(
            7,
            "red",
            70,
            step="awaiting_target",
            scan_type="normal",
        )
        original = dict(wizard)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine") as target_engine,
            patch.object(telegram_bot, "task_queue") as task_queue,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        self.assertEqual(target_engine.method_calls, [])
        self.assertEqual(task_queue.method_calls, [])
        audit.assert_not_called()
        create_task.assert_not_called()
        self.assertIn(
            "bloqueado", update.message.reply_text.await_args.args[0].lower()
        )

    async def test_red_delivery_failure_keeps_single_success_audit(self):
        update = make_text_update("8.8.8.8")
        update.message.reply_text.side_effect = RuntimeError("delivery failed")
        telegram_bot._new_wizard(
            7,
            "red",
            70,
            step="awaiting_target",
            scan_type="normal",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.target_engine, "set_target"),
            patch.object(
                telegram_bot.task_queue,
                "submit",
                return_value="RED-1",
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(asyncio, "create_task") as create_task,
        ):
            with self.assertRaisesRegex(RuntimeError, "delivery failed"):
                await telegram_bot.handle_text(update, None)

        self.assertEqual(
            [call.args[4] for call in audit.call_args_list], ["ok"]
        )
        create_task.assert_not_called()

    async def test_red_task_failure_has_single_error_audit(self):
        update = make_text_update("8.8.8.8")
        telegram_bot._new_wizard(
            7,
            "red",
            70,
            step="awaiting_target",
            scan_type="normal",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.target_engine, "set_target"),
            patch.object(
                telegram_bot.task_queue,
                "submit",
                side_effect=RuntimeError("submit failed"),
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertEqual(
            [call.args[4] for call in audit.call_args_list], ["error"]
        )
        self.assertEqual(
            update.message.reply_text.await_args_list[-1].args[0],
            "Menú principal:",
        )
        self.assertIs(
            update.message.reply_text.await_args_list[-1].kwargs[
                "reply_markup"
            ],
            telegram_bot.MAIN_KEYBOARD,
        )

    async def test_main_button_is_not_consumed_as_wizard_input(self):
        update = make_text_update("🔑 Crack")
        telegram_bot._new_wizard(
            7,
            "web",
            70,
            step="awaiting_target",
            audit_type="vuln",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_text(update, None)

        self.assertEqual(telegram_bot.user_wizards[7]["type"], "crack")
        self.assertEqual(telegram_bot.user_wizards[7]["step"], "select_type")

    async def test_direct_nmap_keeps_default_poll_return_behavior(self):
        update = make_text_update("/nmap quick 8.8.8.8")
        acknowledgement = Mock(name="acknowledgement")
        update.message.reply_text.return_value = acknowledgement
        context = SimpleNamespace(args=["quick", "8.8.8.8"])
        poll_request = Mock(name="poll_request")

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.task_queue,
                "submit",
                return_value="NMAP-1",
            ),
            patch.object(telegram_bot.audit_log, "log"),
            patch.object(
                telegram_bot,
                "_poll_nmap_task",
                new=Mock(return_value=poll_request),
            ) as poll,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.nmap_shortcut(update, context)

        poll.assert_called_once_with(acknowledgement, "NMAP-1")
        create_task.assert_called_once_with(poll_request)

    async def test_old_recon_depth_callback_is_rejected(self):
        wizard = telegram_bot._new_wizard(
            7,
            "recon",
            70,
            step="awaiting_target",
            scan_type="quick",
        )
        original = dict(wizard)
        data = telegram_bot._wizard_callback(wizard, "depth", "normal")
        update, query = make_callback_update(data)
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot, "target_engine") as target_engine,
            patch.object(telegram_bot, "task_queue") as task_queue,
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(telegram_bot.user_wizards[7], wizard)
        self.assertEqual(wizard, original)
        self.assertEqual(target_engine.method_calls, [])
        self.assertEqual(task_queue.method_calls, [])
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])

    async def test_stale_payload_callback_returns_expired_message(self):
        update, query = make_callback_update("wizard:payload:lang:bash")

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)

        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])
        self.assertIn("expir", query.answer.await_args.args[0].lower())

    async def test_crack_type_keyboard_exposes_only_hash(self):
        update = make_text_update("unused")

        await telegram_bot._start_crack_wizard(update, 7)

        wizard = telegram_bot.user_wizards[7]
        self.assertEqual(wizard.get("chat_id"), 70)
        self.assertTrue(wizard.get("session_id"))
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        labels = [
            button.text for row in markup.inline_keyboard for button in row
        ]
        self.assertIn("Hash", " ".join(labels))
        self.assertNotIn("ZIP", " ".join(labels))
        self.assertNotIn("Documento", " ".join(labels))

    async def test_crack_hash_type_updates_existing_session(self):
        _, query = make_callback_update("unused")
        wizard = telegram_bot._new_wizard(7, "crack", 70)

        await telegram_bot._handle_crack_type(query, 7, wizard, "hash")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "awaiting_value")
        self.assertEqual(wizard["crack_type"], "hash")

    async def test_manipulated_crack_type_is_rejected_without_mutation(self):
        _, query = make_callback_update("unused")
        wizard = telegram_bot._new_wizard(7, "crack", 70)

        await telegram_bot._handle_crack_type(query, 7, wizard, "zip")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "select_type")
        self.assertNotIn("crack_type", wizard)
        self.assertIn("no permitido", query.edit_message_text.await_args.args[0].lower())

    async def test_valid_hash_exposes_only_integrated_and_custom_dictionaries(self):
        update = make_text_update("5d41402abc4b2a76b9719d911017c592")
        wizard = telegram_bot._new_wizard(
            7, "crack", 70, step="awaiting_value", crack_type="hash"
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "select_dict")
        self.assertEqual(wizard["algorithm"], "MD5")
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        buttons = [button for row in markup.inline_keyboard for button in row]
        labels = " ".join(button.text for button in buttons)
        callbacks = {button.callback_data for button in buttons}
        self.assertIn("Integrado", labels)
        self.assertIn("Custom", labels)
        self.assertNotIn("rockyou", labels.lower())
        self.assertNotIn("passwords", labels.lower())
        self.assertIn(
            telegram_bot._wizard_callback(
                wizard, "method", "integrated"
            ),
            callbacks,
        )
        self.assertIn(
            telegram_bot._wizard_callback(wizard, "method", "custom"),
            callbacks,
        )

    async def test_invalid_hash_keeps_crack_wizard_awaiting_value(self):
        update = make_text_update("archive.zip")
        wizard = telegram_bot._new_wizard(
            7, "crack", 70, step="awaiting_value", crack_type="hash"
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "awaiting_value")
        self.assertIsNone(wizard["target"])
        self.assertIn("no soportado", update.message.reply_text.await_args.args[0].lower())
        hash_crack.assert_not_called()

    async def test_integrated_crack_consumes_session_before_hash_io(self):
        _, query = make_callback_update("unused")
        events = []

        async def record_edit(text, **kwargs):
            events.append(("edit", text, kwargs))

        query.edit_message_text.side_effect = record_edit
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )

        def crack_after_consume(value):
            self.assertNotIn(7, telegram_bot.user_wizards)
            events.append(("crack", value))
            return {
                "hash": value,
                "identified": [{"type": "MD5"}],
                "cracked": True,
                "plaintext": "hello",
                "algorithm": "MD5",
            }

        with (
            patch.object(
                telegram_bot.hacking.crypto,
                "hash_crack",
                side_effect=crack_after_consume,
            ) as hash_crack,
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot._execute_crack(query, 7, wizard, "integrated")

        hash_crack.assert_called_once_with(wizard["target"])
        self.assertEqual(events[0][0], "edit")
        self.assertIn("analizando hash", events[0][1].lower())
        self.assertNotIn("%", events[0][1])
        self.assertEqual(events[1], ("crack", wizard["target"]))
        self.assertEqual(events[2][0], "edit")
        self.assertIn("hello", events[2][1])
        query.message.reply_text.assert_awaited_once_with(
            "Menú principal:", reply_markup=telegram_bot.MAIN_KEYBOARD
        )

    async def test_integrated_crack_failure_returns_to_main_menu(self):
        _, query = make_callback_update("unused")
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )

        with (
            patch.object(
                telegram_bot.hacking.crypto,
                "hash_crack",
                side_effect=RuntimeError("tool failed"),
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot._execute_crack(
                query, 7, wizard, "integrated"
            )

        self.assertNotIn(7, telegram_bot.user_wizards)
        self.assertEqual(audit.call_args.args[4], "error")
        self.assertIn(
            "analizando hash",
            query.edit_message_text.await_args_list[0].args[0].lower(),
        )
        query.message.reply_text.assert_awaited_once_with(
            "Menú principal:", reply_markup=telegram_bot.MAIN_KEYBOARD
        )

    async def test_integrated_callback_routes_the_exact_wizard(self):
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )
        data = telegram_bot._wizard_callback(
            wizard, "method", "integrated"
        )
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot, "_execute_crack", new=AsyncMock()
            ) as execute_crack,
        ):
            await telegram_bot.handle_callback(update, None)

        execute_crack.assert_awaited_once_with(
            query,
            7,
            wizard,
            "integrated",
            consumed_wizard=wizard,
        )

    async def test_integrated_callback_consumes_before_answer_then_runs_tool(self):
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )
        data = telegram_bot._wizard_callback(
            wizard, "method", "integrated"
        )
        update, query = make_callback_update(data)
        events = []

        async def answer_after_consume(*args, **kwargs):
            self.assertNotIn(7, telegram_bot.user_wizards)
            events.append("answer")

        def crack_after_answer(value):
            self.assertEqual(events, ["answer"])
            events.append("tool")
            return {
                "hash": value,
                "identified": [{"type": "MD5"}],
                "cracked": True,
                "plaintext": "hello",
                "algorithm": "MD5",
            }

        query.answer.side_effect = answer_after_consume
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.crypto,
                "hash_crack",
                side_effect=crack_after_answer,
            ) as hash_crack,
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertEqual(events, ["answer", "tool"])
        query.answer.assert_awaited_once_with()
        hash_crack.assert_called_once_with(wizard["target"])
        self.assertNotIn(7, telegram_bot.user_wizards)

    async def test_manipulated_crack_method_never_reaches_hash_crack(self):
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )
        data = telegram_bot._wizard_callback(
            wizard, "method", "passwords"
        )
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
        ):
            await telegram_bot.handle_callback(update, None)

        hash_crack.assert_not_called()
        self.assertIs(wizard, telegram_bot.user_wizards[7])
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])
        self.assertIn("expir", query.answer.await_args.args[0].lower())

    async def test_manipulated_crack_type_and_method_never_execute(self):
        with patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack:
            for action, value, step in (
                ("type", "zip", "select_type"),
                ("type", "doc", "select_type"),
                ("method", "rockyou", "select_dict"),
                ("method", "bogus", "select_dict"),
            ):
                wizard = telegram_bot._new_wizard(
                    7,
                    "crack",
                    70,
                    step=step,
                    crack_type="hash",
                    target="5d41402abc4b2a76b9719d911017c592",
                )
                data = f"w:{wizard['session_id']}:crack:{action}:{value}"
                update, _ = make_callback_update(data)
                with (
                    patch.object(telegram_bot, "_check_role", return_value=True),
                    patch.object(
                        telegram_bot, "_rate_limit_msg", return_value=None
                    ),
                ):
                    await telegram_bot.handle_callback(update, None)
        hash_crack.assert_not_called()

    async def test_manipulated_crack_type_never_reaches_hash_crack(self):
        _, query = make_callback_update("unused")
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="zip",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )

        with (
            patch.object(
                telegram_bot.hacking.crypto, "hash_crack"
            ) as hash_crack,
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot._execute_crack(
                query, 7, wizard, "integrated"
            )

        hash_crack.assert_not_called()
        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertIn("no permitido", query.edit_message_text.await_args.args[0].lower())

    async def test_stale_crack_session_cannot_consume_replacement(self):
        _, query = make_callback_update("unused")
        stale = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )
        replacement = telegram_bot._new_wizard(7, "web", 70)

        with (
            patch.object(
                telegram_bot.hacking.crypto, "hash_crack"
            ) as hash_crack,
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot._execute_crack(
                query, 7, stale, "integrated"
            )

        hash_crack.assert_not_called()
        self.assertIs(replacement, telegram_bot.user_wizards[7])
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])
        self.assertIn("expiro", query.answer.await_args.args[0].lower())

    async def test_document_does_not_mutate_hash_wizard(self):
        update = make_text_update("unused")
        update.message.document = SimpleNamespace(file_name="archive.zip")
        wizard = telegram_bot._new_wizard(
            7, "crack", 70, step="awaiting_value", crack_type="hash"
        )
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
        ):
            await telegram_bot.handle_document(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        hash_crack.assert_not_called()

    async def test_document_does_not_consume_manipulated_file_wizard(self):
        update = make_text_update("unused")
        get_file = AsyncMock()
        update.message.document = SimpleNamespace(
            file_name="archive.zip", get_file=get_file
        )
        wizard = telegram_bot._new_wizard(
            7, "crack", 70, step="awaiting_value", crack_type="zip"
        )
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
        ):
            await telegram_bot.handle_document(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        get_file.assert_not_awaited()
        hash_crack.assert_not_called()

    async def test_custom_dictionary_waits_for_words_and_passes_them(self):
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )
        data = telegram_bot._wizard_callback(wizard, "method", "custom")
        callback_update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
        ):
            await telegram_bot.handle_callback(callback_update, None)

        hash_crack.assert_not_called()
        self.assertEqual(telegram_bot.user_wizards[7]["step"], "awaiting_dictionary")
        query.answer.assert_awaited_once_with()

        text_update = make_text_update("hello, secret")
        events = []

        async def record_reply(text, **kwargs):
            events.append(("reply", text, kwargs))

        text_update.message.reply_text.side_effect = record_reply
        result = {
            "hash": "5d41402abc4b2a76b9719d911017c592",
            "identified": [{"type": "MD5"}],
            "cracked": True,
            "plaintext": "hello",
            "algorithm": "MD5",
        }

        def crack_after_consume(value, words):
            self.assertNotIn(7, telegram_bot.user_wizards)
            events.append(("crack", value, words))
            return result

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.crypto,
                "hash_crack",
                side_effect=crack_after_consume,
            ) as hash_crack,
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot.handle_text(text_update, None)

        hash_crack.assert_called_once_with(
            "5d41402abc4b2a76b9719d911017c592", ["hello", "secret"]
        )
        self.assertNotIn(7, telegram_bot.user_wizards)
        self.assertEqual(events[0][0], "reply")
        self.assertIn("analizando hash", events[0][1].lower())
        self.assertNotIn("%", events[0][1])
        self.assertEqual(events[1][0], "crack")
        self.assertEqual(events[2][0], "reply")
        self.assertIn("hello", events[2][1])
        self.assertEqual(events[3][0], "reply")
        self.assertEqual(events[3][1], "Menú principal:")
        self.assertIs(
            events[3][2]["reply_markup"], telegram_bot.MAIN_KEYBOARD
        )

    async def test_empty_custom_dictionary_remains_retryable(self):
        update = make_text_update(" , \n , ")
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="awaiting_dictionary",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.crypto, "hash_crack"
            ) as hash_crack,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "awaiting_dictionary")
        hash_crack.assert_not_called()
        self.assertIn(
            "al menos una palabra",
            update.message.reply_text.await_args.args[0].lower(),
        )

    async def test_custom_dictionary_failure_is_labeled_custom(self):
        update = make_text_update("guess")
        telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="awaiting_dictionary",
            crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )
        result = {
            "hash": "5d41402abc4b2a76b9719d911017c592",
            "identified": [{"type": "MD5"}],
            "cracked": False,
            "algorithm": "MD5",
        }

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.hacking.crypto,
                "hash_crack",
                return_value=result,
            ),
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot.handle_text(update, None)

        rendered = update.message.reply_text.await_args_list[1].args[0]
        self.assertIn("custom", rendered.lower())
        self.assertNotIn("integrado", rendered.lower())

    async def test_custom_dictionary_revalidates_stored_hash_before_io(self):
        update = make_text_update("hello, secret")
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="awaiting_dictionary",
            crack_type="hash",
            target="$2b12$" + "a" * 53,
            algorithm="MD5",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
        ):
            await telegram_bot.handle_text(update, None)

        hash_crack.assert_not_called()
        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertIn("no soportado", update.message.reply_text.await_args.args[0].lower())

    async def test_custom_dictionary_rejects_manipulated_crack_type(self):
        update = make_text_update("hello")
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="awaiting_dictionary",
            crack_type="zip",
            target="5d41402abc4b2a76b9719d911017c592",
            algorithm="MD5",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
        ):
            await telegram_bot.handle_text(update, None)

        hash_crack.assert_not_called()
        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertIn("no permitido", update.message.reply_text.await_args.args[0].lower())

    async def test_osint_menu_exposes_only_email_and_domain(self):
        update = make_text_update("unused")

        await telegram_bot._start_osint_wizard(update, 7)

        wizard = telegram_bot.user_wizards[7]
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        choices = [
            (button.text, button.callback_data)
            for row in markup.inline_keyboard
            for button in row
            if f":{wizard['type']}:type:" in button.callback_data
        ]
        self.assertEqual(
            choices,
            [
                (
                    "📧 Email",
                    telegram_bot._wizard_callback(
                        wizard, "type", "email"
                    ),
                ),
                (
                    "🌐 Dominio",
                    telegram_bot._wizard_callback(
                        wizard, "type", "domain"
                    ),
                ),
            ],
        )

    async def test_forged_osint_person_callback_is_rejected(self):
        wizard = telegram_bot._new_wizard(7, "osint", 70)
        original = dict(wizard)
        data = telegram_bot._wizard_callback(wizard, "type", "person")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])

    async def test_osint_email_selection_asks_for_email(self):
        wizard = telegram_bot._new_wizard(7, "osint", 70)
        data = telegram_bot._wizard_callback(wizard, "type", "email")
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
        ):
            await telegram_bot.handle_callback(update, None)

        self.assertEqual(wizard["step"], "awaiting_target")
        self.assertEqual(wizard["osint_type"], "email")
        self.assertIn(
            "email", query.edit_message_text.await_args.args[0].lower()
        )

    async def test_osint_invalid_email_remains_retryable(self):
        for value in (
            "user@example",
            "user name@example.com",
            "@example.com",
            "user@.com",
        ):
            with self.subTest(value=value):
                telegram_bot.user_wizards.clear()
                update = make_text_update(value)
                wizard = telegram_bot._new_wizard(
                    7,
                    "osint",
                    70,
                    step="awaiting_target",
                    osint_type="email",
                )
                original = dict(wizard)
                with (
                    patch.object(
                        telegram_bot, "_check_role", return_value=True
                    ),
                    patch.object(
                        telegram_bot,
                        "_rate_limit_msg",
                        return_value=None,
                    ),
                    patch.object(
                        asyncio, "to_thread", new=AsyncMock()
                    ) as to_thread,
                    patch.object(telegram_bot, "target_engine") as target_engine,
                    patch.object(telegram_bot, "task_queue") as task_queue,
                ):
                    await telegram_bot.handle_text(update, None)

                self.assertIs(wizard, telegram_bot.user_wizards[7])
                self.assertEqual(wizard, original)
                to_thread.assert_not_awaited()
                self.assertEqual(target_engine.method_calls, [])
                self.assertEqual(task_queue.method_calls, [])

    async def test_osint_valid_email_uses_real_result_and_returns_to_menu(self):
        update = make_text_update("user@example.com")
        status_message = SimpleNamespace(edit_text=AsyncMock())

        async def reply_after_consume(*args, **kwargs):
            self.assertNotIn(7, telegram_bot.user_wizards)
            return status_message

        update.message.reply_text.side_effect = reply_after_consume
        telegram_bot._new_wizard(
            7,
            "osint",
            70,
            step="awaiting_target",
            osint_type="email",
        )
        result = {
            "email": "user@example.com",
            "username": "user",
            "domain": "example.com",
            "mx_records": ["mx1.example.com.", "mx2.example.com."],
            "dominio_info": {
                "subdominios_cert": [
                    "api.example.com",
                    "www.example.com",
                ],
                "total_certs": 12,
            },
        }

        async def execute_after_consume(function, target):
            self.assertNotIn(7, telegram_bot.user_wizards)
            return result

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.target_engine, "set_target"
            ) as set_target,
            patch.object(telegram_bot.task_queue, "submit") as submit,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(
                asyncio,
                "to_thread",
                new=AsyncMock(side_effect=execute_after_consume),
            ) as to_thread,
        ):
            await telegram_bot.handle_text(update, None)

        to_thread.assert_awaited_once_with(
            telegram_bot.hacking.osint.email_osint, "user@example.com"
        )
        set_target.assert_called_once_with(
            7, "user@example.com", "email"
        )
        submit.assert_not_called()
        self.assertNotIn(7, telegram_bot.user_wizards)
        self.assertIn(
            "consultando",
            update.message.reply_text.await_args_list[0].args[0].lower(),
        )
        rendered = status_message.edit_text.await_args.args[0]
        self.assertIn("mx1.example.com.", rendered)
        self.assertIn("mx2.example.com.", rendered)
        self.assertIn("api.example.com", rendered)
        self.assertIn("www.example.com", rendered)
        self.assertIn("12", rendered)
        self.assertEqual(
            audit.call_args.args[2:5],
            ("wizard:osint:email", "user@example.com", "ok"),
        )
        menu = update.message.reply_text.await_args_list[-1]
        self.assertEqual(menu.args[0], "Menú principal:")
        self.assertIs(
            menu.kwargs["reply_markup"], telegram_bot.MAIN_KEYBOARD
        )

    async def test_osint_email_unavailable_result_returns_to_menu(self):
        update = make_text_update("user@example.com")
        status_message = SimpleNamespace(edit_text=AsyncMock())
        update.message.reply_text.return_value = status_message
        telegram_bot._new_wizard(
            7,
            "osint",
            70,
            step="awaiting_target",
            osint_type="email",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.target_engine, "set_target"),
            patch.object(
                asyncio,
                "to_thread",
                new=AsyncMock(
                    return_value={"error": "servicio no disponible"}
                ),
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertIsNotNone(
            status_message.edit_text.await_args,
            "OSINT email result was not rendered",
        )
        self.assertIn(
            "servicio no disponible",
            status_message.edit_text.await_args.args[0],
        )
        self.assertEqual(audit.call_args.args[4], "error")
        menu = update.message.reply_text.await_args_list[-1]
        self.assertIs(
            menu.kwargs["reply_markup"], telegram_bot.MAIN_KEYBOARD
        )

    async def test_osint_valid_domain_submits_normal_playbook_and_polls(self):
        update = make_text_update("example.com")
        acknowledgement = Mock(name="acknowledgement")
        update.message.reply_text.return_value = acknowledgement
        telegram_bot._new_wizard(
            7,
            "osint",
            70,
            step="awaiting_target",
            osint_type="domain",
        )

        def persist_after_consume(uid, target, target_type):
            self.assertNotIn(7, telegram_bot.user_wizards)

        def submit_after_consume(task_type, target, params):
            self.assertNotIn(7, telegram_bot.user_wizards)
            return "OSINT-1"

        poll_request = Mock(name="poll_request")
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.target_engine,
                "set_target",
                side_effect=persist_after_consume,
            ) as set_target,
            patch.object(
                telegram_bot.task_queue,
                "submit",
                side_effect=submit_after_consume,
            ) as submit,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(
                telegram_bot,
                "_poll_playbook_task",
                new=Mock(return_value=poll_request),
            ) as poll,
            patch.object(asyncio, "create_task") as create_task,
        ):
            await telegram_bot.handle_text(update, None)

        set_target.assert_called_once_with(7, "example.com", "domain")
        submit.assert_called_once_with(
            "playbook",
            "example.com",
            {"playbook": "osint_domain", "depth": "normal", "user_id": 7},
        )
        audit.assert_not_called()
        poll.assert_called_once_with(
            acknowledgement,
            "OSINT-1",
            "OSINT de Dominio",
            return_to_menu=True,
            uid=7,
        )
        create_task.assert_called_once_with(poll_request)

    async def test_osint_invalid_domain_or_ip_remains_retryable(self):
        for value in (
            "8.8.8.8",
            "8.8.8.0/24",
            "192.168.1.20",
            "not a domain",
        ):
            with self.subTest(value=value):
                telegram_bot.user_wizards.clear()
                update = make_text_update(value)
                wizard = telegram_bot._new_wizard(
                    7,
                    "osint",
                    70,
                    step="awaiting_target",
                    osint_type="domain",
                )
                original = dict(wizard)
                with (
                    patch.object(
                        telegram_bot, "_check_role", return_value=True
                    ),
                    patch.object(
                        telegram_bot,
                        "_rate_limit_msg",
                        return_value=None,
                    ),
                    patch.object(telegram_bot, "target_engine") as target_engine,
                    patch.object(telegram_bot, "task_queue") as task_queue,
                    patch.object(asyncio, "create_task") as create_task,
                ):
                    await telegram_bot.handle_text(update, None)

                self.assertIs(wizard, telegram_bot.user_wizards[7])
                self.assertEqual(wizard, original)
                self.assertEqual(target_engine.method_calls, [])
                self.assertEqual(task_queue.method_calls, [])
                create_task.assert_not_called()

    async def test_osint_domain_submit_failure_returns_to_menu(self):
        update = make_text_update("example.com")
        telegram_bot._new_wizard(
            7,
            "osint",
            70,
            step="awaiting_target",
            osint_type="domain",
        )

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.target_engine, "set_target"),
            patch.object(
                telegram_bot.task_queue,
                "submit",
                side_effect=RuntimeError("submit failed"),
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot.handle_text(update, None)

        self.assertTrue(audit.called, "OSINT domain failure was not audited")
        self.assertEqual(audit.call_args.args[4], "error")
        menu = update.message.reply_text.await_args_list[-1]
        self.assertIs(
            menu.kwargs["reply_markup"], telegram_bot.MAIN_KEYBOARD
        )

    async def test_osint_depth_callback_is_rejected_without_execution(self):
        wizard = telegram_bot._new_wizard(
            7,
            "osint",
            70,
            step="awaiting_depth",
            target="example.com",
            osint_type="domain",
        )
        original = dict(wizard)
        data = telegram_bot._wizard_callback(
            wizard, "depth", "normal"
        )
        update, query = make_callback_update(data)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.task_queue, "submit", return_value="OLD-1"
            ) as submit,
            patch.object(telegram_bot.target_engine, "set_target"),
            patch.object(telegram_bot.audit_log, "log"),
        ):
            await telegram_bot.handle_callback(update, None)

        submit.assert_not_called()
        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        query.edit_message_text.assert_not_awaited()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.await_args.kwargs["show_alert"])

    def test_production_has_no_obsolete_depth_wizard_routes(self):
        source = inspect.getsource(telegram_bot)

        self.assertFalse(hasattr(telegram_bot, "_depth_keyboard"))
        self.assertNotIn("awaiting_depth", source)

    async def test_cracked_hash_is_audited_as_success(self):
        result = {
            "hash": "5d41402abc4b2a76b9719d911017c592",
            "identified": [{"type": "MD5"}],
            "cracked": True,
            "plaintext": "hello",
            "algorithm": "MD5",
        }
        wizard = telegram_bot._new_wizard(
            7,
            "crack",
            70,
            step="select_dict",
            crack_type="hash",
            target=result["hash"],
            algorithm="MD5",
        )
        data = telegram_bot._wizard_callback(
            wizard, "method", "integrated"
        )
        _, query = make_callback_update(data)

        with (
            patch.object(
                telegram_bot.hacking.crypto,
                "hash_crack",
                return_value=result,
            ),
            patch.object(telegram_bot.audit_log, "log") as audit,
        ):
            await telegram_bot._execute_crack(
                query, 7, wizard, "integrated"
            )

        self.assertEqual(audit.call_args.args[4], "ok")
        self.assertEqual(audit.call_args.args[3], result["hash"])

    def test_red_production_has_no_wifi_simulation_paths(self):
        source = inspect.getsource(telegram_bot)

        for function_name in (
            "_scan_available_wifi",
            "_simulate_wifi_crack",
            "_execute_red",
        ):
            with self.subTest(function_name=function_name):
                self.assertFalse(hasattr(telegram_bot, function_name))
        for obsolete_path in (
            "scan_wifi",
            "crack_wifi",
            "scan_lan",
            "password123",
        ):
            with self.subTest(obsolete_path=obsolete_path):
                self.assertNotIn(obsolete_path, source)

    async def test_safe_delivery_retries_only_entity_parse_errors(self):
        method = AsyncMock(
            side_effect=[BadRequest("Can't parse entities"), None]
        )
        markup = object()

        await telegram_bot._safe_telegram_call(
            method,
            "bad_markdown",
            parse_mode="Markdown",
            reply_markup=markup,
        )

        self.assertEqual(method.await_count, 2)
        self.assertNotIn("parse_mode", method.await_args_list[1].kwargs)
        self.assertIs(
            method.await_args_list[1].kwargs["reply_markup"], markup
        )

    async def test_safe_delivery_does_not_retry_unrelated_bad_request(self):
        method = AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )

        with self.assertRaises(BadRequest):
            await telegram_bot._safe_telegram_call(
                method, "same", parse_mode="Markdown"
            )

        self.assertEqual(method.await_count, 1)

    async def test_safe_delivery_without_parse_mode_does_not_retry(self):
        method = AsyncMock(
            side_effect=BadRequest("Can't parse entities")
        )

        with self.assertRaises(BadRequest):
            await telegram_bot._safe_telegram_call(method, "plain")

        self.assertEqual(method.await_count, 1)

    async def test_playbook_poll_reports_real_progress_result_and_menu(self):
        poller = getattr(telegram_bot, "_poll_playbook_task", None)
        self.assertIsNotNone(poller, "generic playbook poller is missing")
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )
        progress = {
            "status": "queued",
            "progress": 30,
            "current_step": "Enumeration DNS",
        }
        completed = {
            "status": "completed",
            "target": "example.com",
            "result": {
                "target": "example.com",
                "summary": (
                    "Playbook: Reconocimiento Web (domain)\n"
                    "Pasos completados: 1/2"
                ),
                "results": [
                    {
                        "label": "Enumeration DNS",
                        "success": True,
                        "note": None,
                    },
                    {
                        "label": "Descubrimiento de Subdominios",
                        "success": False,
                        "note": "sin datos",
                    },
                ],
            },
        }

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                side_effect=[
                    progress,
                    {**progress, "status": "running"},
                    completed,
                ],
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            await poller(
                message,
                "WEB-1",
                "Reconocimiento Web",
                return_to_menu=True,
            )

        self.assertEqual(sleep.await_args_list[0].args, (2,))
        self.assertEqual(message.edit_text.await_count, 2)
        progress_text = message.edit_text.await_args_list[0].args[0]
        self.assertIn("30%", progress_text)
        self.assertIn("Enumeration DNS", progress_text)
        bar = re.search(r"\[([█░]+)\]", progress_text)
        self.assertIsNotNone(bar)
        self.assertEqual(len(bar.group(1)), 10)
        self.assertEqual(bar.group(1), "███░░░░░░░")

        completion = message.edit_text.await_args_list[1].args[0]
        self.assertIn("example.com", completion)
        self.assertIn("Playbook: Reconocimiento Web", completion)
        self.assertIn("[OK] Enumeration DNS", completion)
        self.assertIn(
            "[SKIP] Descubrimiento de Subdominios - sin datos",
            completion,
        )
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_playbook_poll_renders_real_error_contract_as_skip_note(self):
        from playbooks import run_playbook

        hacking_module = SimpleNamespace(
            dns_enum=lambda target: {"error": "DNS unavailable"},
            subdomain_scan=lambda target: ["www.example.com"],
            cert_transparency=lambda target: [
                "Error: certificate service unavailable"
            ],
            ip_geo=lambda target: {"country": "US"},
        )
        result = run_playbook(
            "osint_domain",
            "example.com",
            hacking_module=hacking_module,
        )
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                return_value={
                    "status": "completed",
                    "target": "example.com",
                    "result": result,
                },
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_playbook_task(
                message,
                "OSINT-ERROR",
                "OSINT de Dominio",
                return_to_menu=True,
            )

        completion = message.edit_text.await_args.args[0]
        self.assertIn(
            "[SKIP] Enumeration DNS - DNS unavailable", completion
        )
        self.assertIn(
            "[SKIP] Transparencia de Certificados - "
            "Error: certificate service unavailable",
            completion,
        )
        self.assertNotIn("[OK] Enumeration DNS", completion)
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_recon_transport_outage_flows_through_queue_to_telegram_failure(self):
        queue = TaskQueue.__new__(TaskQueue)
        queue._tasks = {}
        queue._queue = []
        queue._lock = threading.Lock()
        queue._save = Mock()
        target = "https://example.com/search?q=1"
        task_id = queue.submit(
            "playbook",
            target,
            {"playbook": "recon_web", "depth": "normal"},
        )

        def fail_resolution(*args, **kwargs):
            raise socket.gaierror(
                socket.EAI_AGAIN, "temporary resolver failure"
            )

        with (
            patch.object(
                dns.resolver,
                "resolve",
                side_effect=TimeoutError("resolver unavailable"),
            ),
            patch.object(
                network_hacking.socket,
                "getaddrinfo",
                side_effect=fail_resolution,
            ),
            patch.object(
                network_hacking.socket,
                "gethostbyname",
                side_effect=fail_resolution,
            ),
            patch.object(
                web_hacking,
                "_http_get",
                return_value=(0, {}, "connection refused"),
            ),
            patch.object(web_hacking, "COMMON_DIRS", ["admin", "login"]),
            patch.object(
                web_hacking.urllib.request,
                "urlopen",
                side_effect=OSError("connection refused"),
            ),
        ):
            await asyncio.to_thread(
                queue._run_playbook_task,
                task_id,
                target,
                {"playbook": "recon_web", "depth": "normal"},
            )

        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )
        with (
            patch.object(telegram_bot, "task_queue", queue),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_playbook_task(
                message,
                task_id,
                "Reconocimiento Web",
            )

        rendered = message.edit_text.await_args.args[0]
        self.assertIn("falló", rendered)
        self.assertIn("Todos los pasos", rendered)
        self.assertEqual(queue.get_status(task_id)["status"], "failed")

    async def test_recon_partial_dns_results_survive_queue_and_telegram_rendering(self):
        queue = TaskQueue.__new__(TaskQueue)
        queue._tasks = {}
        queue._queue = []
        queue._lock = threading.Lock()
        queue._save = Mock()
        target = "https://example.com/search?q=1"
        task_id = queue.submit(
            "playbook",
            target,
            {"playbook": "recon_web", "depth": "normal"},
        )

        def mixed_dns_resolution(domain, record_type, lifetime):
            if record_type == "A":
                return ["93.184.216.34"]
            if record_type == "AAAA":
                raise TimeoutError("resolver unavailable")
            raise dns.resolver.NoAnswer()

        def mixed_subdomain_resolution(host, *args, **kwargs):
            if host == "www.example.com":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ())]
            if host == "api.example.com":
                raise socket.gaierror(
                    socket.EAI_AGAIN, "temporary resolver failure"
                )
            raise socket.gaierror(socket.EAI_NONAME, "name does not exist")

        def fail_resolution(*args, **kwargs):
            raise socket.gaierror(
                socket.EAI_AGAIN, "temporary resolver failure"
            )

        with (
            patch.object(
                dns.resolver,
                "resolve",
                side_effect=mixed_dns_resolution,
            ),
            patch.object(
                network_hacking.socket,
                "getaddrinfo",
                side_effect=mixed_subdomain_resolution,
            ),
            patch.object(
                network_hacking.socket,
                "gethostbyname",
                side_effect=fail_resolution,
            ),
            patch.object(
                web_hacking,
                "_http_get",
                return_value=(0, {}, "connection refused"),
            ),
            patch.object(web_hacking, "COMMON_DIRS", ["admin", "login"]),
            patch.object(
                web_hacking.urllib.request,
                "urlopen",
                side_effect=OSError("connection refused"),
            ),
        ):
            await asyncio.to_thread(
                queue._run_playbook_task,
                task_id,
                target,
                {"playbook": "recon_web", "depth": "normal"},
            )

        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )
        with (
            patch.object(telegram_bot, "task_queue", queue),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_playbook_task(
                message,
                task_id,
                "Reconocimiento Web",
            )

        status = queue.get_status(task_id)
        rendered = message.edit_text.await_args.args[0]
        self.assertIn("completado", rendered)
        self.assertEqual(status["status"], "completed")
        steps = {
            step["step_id"]: step
            for step in status["result"]["results"]
        }
        self.assertTrue(steps["dns"]["success"])
        self.assertEqual(steps["dns"]["data"]["A"], ["93.184.216.34"])
        self.assertIn("Parcial:", steps["dns"]["note"])
        self.assertTrue(steps["subdomains"]["success"])
        self.assertEqual(
            steps["subdomains"]["data"]["found"],
            ["www.example.com"],
        )
        self.assertIn("Parcial:", steps["subdomains"]["note"])
        self.assertIn("[OK] Enumeration DNS - Parcial:", rendered)
        self.assertIn(
            "[OK] Descubrimiento de Subdominios - Parcial:",
            rendered,
        )

    async def test_playbook_poll_failure_is_terminal_and_returns_to_menu(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )
        completed_sentinel = {
            "status": "completed",
            "target": "should-not-be-read.example",
            "result": {},
        }

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                side_effect=[
                    {"status": "failed", "error": "playbook failed"},
                    completed_sentinel,
                ],
            ) as get_status,
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_playbook_task(
                message,
                "WEB-FAIL",
                "Auditoría de Vulnerabilidades",
                return_to_menu=True,
            )

        get_status.assert_called_once_with("WEB-FAIL")
        self.assertIn("playbook failed", message.edit_text.await_args.args[0])
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_playbook_poll_timeout_is_terminal_and_returns_to_menu(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )
        clock = Mock()
        clock.time.side_effect = [0.0, 1.0]
        completed_sentinel = {
            "status": "completed",
            "target": "should-not-be-read.example",
            "result": {},
        }

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                side_effect=[
                    {
                        "status": "queued",
                        "progress": 0,
                        "current_step": "En cola",
                    },
                    completed_sentinel,
                ],
            ) as get_status,
            patch.object(asyncio, "get_event_loop", return_value=clock),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_playbook_task(
                message,
                "WEB-TIMEOUT",
                "Reconocimiento Web",
                timeout=0,
                return_to_menu=True,
            )

        get_status.assert_called_once_with("WEB-TIMEOUT")
        self.assertIn("Tiempo agotado", message.edit_text.await_args.args[0])
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_playbook_poll_cancelled_and_missing_are_terminal(self):
        terminal_cases = (
            ({"status": "cancelled"}, "cancelada"),
            ({"error": "Tarea no encontrada"}, "Tarea no encontrada"),
        )
        for terminal_status, expected_text in terminal_cases:
            with self.subTest(status=terminal_status):
                message = SimpleNamespace(
                    edit_text=AsyncMock(),
                    reply_text=AsyncMock(),
                )
                with (
                    patch.object(
                        telegram_bot.task_queue,
                        "get_status",
                        side_effect=[
                            terminal_status,
                            {
                                "status": "completed",
                                "target": "should-not-be-read.example",
                                "result": {},
                            },
                        ],
                    ) as get_status,
                    patch.object(asyncio, "sleep", new=AsyncMock()),
                ):
                    await telegram_bot._poll_playbook_task(
                        message,
                        "WEB-TERM",
                        "Reconocimiento Web",
                        return_to_menu=True,
                    )

                get_status.assert_called_once_with("WEB-TERM")
                self.assertIn(
                    expected_text, message.edit_text.await_args.args[0]
                )
                message.reply_text.assert_awaited_once_with(
                    "Menú principal:",
                    reply_markup=telegram_bot.MAIN_KEYBOARD,
                )

    async def test_playbook_poll_continues_after_not_modified_race(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(
                side_effect=[BadRequest("Message is not modified"), None]
            )
        )
        completed = {
            "status": "completed",
            "target": "example.com",
            "result": {"summary": "real summary", "results": []},
        }
        caught = None

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                side_effect=[
                    {
                        "status": "running",
                        "progress": 40,
                        "current_step": "Paso real",
                    },
                    completed,
                ],
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            try:
                await telegram_bot._poll_playbook_task(
                    message, "WEB-RACE", "Reconocimiento Web"
                )
            except BadRequest as exc:
                caught = exc

        self.assertIsNone(caught, "not-modified race must be tolerated")
        self.assertEqual(message.edit_text.await_count, 2)
        self.assertIn("real summary", message.edit_text.await_args.args[0])

    async def test_playbook_poll_propagates_unrelated_bad_request(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(side_effect=BadRequest("Chat not found"))
        )

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                return_value={
                    "status": "running",
                    "progress": 40,
                    "current_step": "Paso real",
                },
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            with self.assertRaisesRegex(BadRequest, "Chat not found"):
                await telegram_bot._poll_playbook_task(
                    message, "WEB-ERROR", "Reconocimiento Web"
                )

        self.assertEqual(message.edit_text.await_count, 1)

    async def test_playbook_poll_caps_completion_without_losing_steps(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        completed = {
            "status": "completed",
            "target": "example.com",
            "result": {
                "summary": "SUMMARY-" + "s" * 5000,
                "results": [
                    {
                        "label": "Real Step Label",
                        "success": False,
                        "note": "REAL-NOTE-" + "n" * 5000,
                    }
                ],
            },
        }

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                return_value=completed,
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_playbook_task(
                message, "WEB-LONG", "Auditoría Web"
            )

        completion = message.edit_text.await_args.args[0]
        self.assertLessEqual(len(completion), 3500)
        self.assertIn("example.com", completion)
        self.assertIn("SUMMARY-", completion)
        self.assertIn("[SKIP] Real Step Label - REAL-NOTE-", completion)

    async def test_nmap_poll_retries_plain_text_after_markdown_error(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(
                side_effect=[BadRequest("Can't parse entities"), None]
            )
        )
        completed = {
            "status": "completed",
            "target": "host_with_underscore.example",
            "params": {"scan_type": "quick"},
            "result": {
                "elapsed": 1.0,
                "parsed": None,
                "stdout": "value_with_underscore",
            },
        }

        with (
            patch.object(telegram_bot.task_queue, "get_status", return_value=completed),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_nmap_task(message, "ABC123")

        self.assertEqual(message.edit_text.await_count, 2)
        self.assertNotIn(
            "parse_mode", message.edit_text.await_args_list[1].kwargs
        )

    async def test_nmap_poll_completion_returns_to_main_menu_when_requested(self):
        self.assertIn(
            "return_to_menu",
            inspect.signature(telegram_bot._poll_nmap_task).parameters,
        )
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )
        completed = {
            "status": "completed",
            "target": "8.8.8.8",
            "params": {"scan_type": "quick"},
            "result": {
                "elapsed": 1.0,
                "parsed": None,
                "stdout": "scan complete",
            },
        }

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                return_value=completed,
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_nmap_task(
                message,
                "RECON-1",
                return_to_menu=True,
            )

        self.assertIn("scan complete", message.edit_text.await_args.args[0])
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_nmap_poll_failure_returns_to_main_menu_when_requested(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                return_value={"status": "failed", "error": "nmap failed"},
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_nmap_task(
                message,
                "RECON-1",
                return_to_menu=True,
            )

        message.edit_text.assert_awaited_once()
        self.assertIn("nmap failed", message.edit_text.await_args.args[0])
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_nmap_poll_missing_task_is_terminal_and_returns_to_menu(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                return_value={"error": "Tarea no encontrada"},
            ) as get_status,
            patch.object(
                asyncio, "sleep", new=AsyncMock()
            ) as sleep,
        ):
            await telegram_bot._poll_nmap_task(
                message,
                "NMAP-MISSING",
                return_to_menu=True,
            )

        get_status.assert_called_once_with("NMAP-MISSING")
        sleep.assert_awaited_once_with(2)
        message.edit_text.assert_awaited_once()
        self.assertIn(
            "tarea no encontrada",
            message.edit_text.await_args.args[0].lower(),
        )
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_nmap_poll_cancelled_is_terminal_and_returns_to_menu(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )
        completed_sentinel = {
            "status": "completed",
            "target": "should-not-be-read.example",
            "result": {},
        }

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                side_effect=[
                    {"status": "cancelled"},
                    completed_sentinel,
                ],
            ) as get_status,
            patch.object(
                asyncio, "sleep", new=AsyncMock()
            ) as sleep,
        ):
            await telegram_bot._poll_nmap_task(
                message,
                "NMAP-CANCELLED",
                return_to_menu=True,
            )

        get_status.assert_called_once_with("NMAP-CANCELLED")
        sleep.assert_awaited_once_with(2)
        message.edit_text.assert_awaited_once()
        self.assertIn(
            "cancelada", message.edit_text.await_args.args[0].lower()
        )
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_nmap_poll_timeout_returns_to_main_menu_when_requested(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(),
            reply_text=AsyncMock(),
        )
        clock = Mock()
        clock.time.side_effect = [0.0, 1.0]

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                return_value={"status": "queued"},
            ),
            patch.object(asyncio, "get_event_loop", return_value=clock),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_nmap_task(
                message,
                "RECON-1",
                timeout=0,
                return_to_menu=True,
            )

        self.assertIn("Tiempo agotado", message.edit_text.await_args.args[0])
        message.reply_text.assert_awaited_once_with(
            "Menú principal:",
            reply_markup=telegram_bot.MAIN_KEYBOARD,
        )

    async def test_nmap_poll_skips_duplicate_progress_and_delivers_completion(self):
        message = SimpleNamespace(edit_text=AsyncMock())
        running = {
            "status": "running",
            "progress": 25,
            "current_step": "Ejecutando nmap...",
        }
        completed = {
            "status": "completed",
            "target": "8.8.8.8",
            "params": {"scan_type": "quick"},
            "result": {
                "elapsed": 1.0,
                "parsed": None,
                "stdout": "scan complete",
            },
        }

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                side_effect=[running, running, completed],
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_nmap_task(message, "ABC123")

        self.assertEqual(message.edit_text.await_count, 2)
        progress = message.edit_text.await_args_list[0].args[0]
        self.assertIn("25%", progress)
        self.assertIn("Ejecutando nmap...", progress)
        bar = re.search(r"\[([█░]+)\]", progress)
        self.assertIsNotNone(bar)
        self.assertEqual(len(bar.group(1)), 10)
        self.assertEqual(bar.group(1), "██░░░░░░░░")
        completion = message.edit_text.await_args_list[1].args[0]
        self.assertIn("Nmap", completion)
        self.assertIn("scan complete", completion)

    async def test_nmap_poll_continues_after_message_not_modified_race(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(
                side_effect=[BadRequest("Message is not modified"), None]
            )
        )
        completed = {
            "status": "completed",
            "target": "8.8.8.8",
            "params": {"scan_type": "quick"},
            "result": {
                "elapsed": 1.0,
                "parsed": None,
                "stdout": "final result",
            },
        }

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                side_effect=[
                    {"status": "running", "progress": 25},
                    completed,
                ],
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            await telegram_bot._poll_nmap_task(message, "ABC123")

        self.assertEqual(message.edit_text.await_count, 2)
        self.assertIn("final result", message.edit_text.await_args.args[0])

    async def test_nmap_poll_propagates_unrelated_bad_request(self):
        message = SimpleNamespace(
            edit_text=AsyncMock(side_effect=BadRequest("Chat not found"))
        )

        with (
            patch.object(
                telegram_bot.task_queue,
                "get_status",
                return_value={"status": "running", "progress": 25},
            ),
            patch.object(asyncio, "sleep", new=AsyncMock()),
        ):
            with self.assertRaisesRegex(BadRequest, "Chat not found"):
                await telegram_bot._poll_nmap_task(message, "ABC123")

        self.assertEqual(message.edit_text.await_count, 1)

    async def test_nmap_confirmation_bad_request_is_not_retried_or_swallowed(self):
        update = make_text_update("/nmap quick 8.8.8.8")
        update.message.reply_text.side_effect = BadRequest("Chat not found")
        context = SimpleNamespace(args=["quick", "8.8.8.8"])

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot.task_queue, "submit", return_value="NMAP-1"
            ) as submit,
            patch.object(telegram_bot.audit_log, "log") as audit,
            patch.object(asyncio, "create_task") as create_task,
        ):
            with self.assertRaisesRegex(BadRequest, "Chat not found"):
                await telegram_bot.nmap_shortcut(update, context)

        submit.assert_called_once_with(
            "nmap", "8.8.8.8", {"scan_type": "quick", "user_id": 7}
        )
        audit.assert_called_once()
        self.assertEqual(update.message.reply_text.await_count, 1)
        create_task.assert_not_called()

    async def test_chat_api_handles_malformed_success_json_once(self):
        update = make_text_update("hello")
        response = Mock(status_code=200)
        response.json.side_effect = ValueError("invalid JSON")
        client = AsyncMock()
        client.__aenter__.return_value.post = AsyncMock(
            return_value=response
        )

        with patch.object(
            telegram_bot.httpx, "AsyncClient", return_value=client
        ):
            await telegram_bot._chat_api(update, "hello")

        update.message.reply_text.assert_awaited_once()
        message = update.message.reply_text.await_args.args[0]
        self.assertIn("respuesta", message.lower())
        self.assertIn("api", message.lower())

    async def test_recon_command_opens_fresh_wizard(self):
        update = make_text_update("/recon")
        telegram_bot.user_wizards[7] = {"type": "stale"}
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                telegram_bot, "_start_recon_wizard", new=AsyncMock()
            ) as start,
        ):
            await telegram_bot.recon_command(update, None)

        self.assertNotIn(7, telegram_bot.user_wizards)
        start.assert_awaited_once_with(update, 7)

    def test_wizard_commands_and_media_handlers_are_registered(self):
        fake_app = SimpleNamespace(handlers=[], run_polling=Mock())
        fake_app.add_handler = fake_app.handlers.append
        builder = Mock()
        builder.token.return_value = builder
        builder.build.return_value = fake_app

        with (
            patch.object(telegram_bot.Application, "builder", return_value=builder),
            patch.dict(os.environ, {"TELEGRAM_TOKEN": "test-token"}),
            patch("builtins.print"),
        ):
            telegram_bot.main()

        command_callbacks = {
            command: handler.callback
            for handler in fake_app.handlers
            for command in getattr(handler, "commands", frozenset())
        }
        self.assertTrue(
            {
                "recon",
                "webscan",
                "web",
                "crack",
                "payload",
                "osint",
                "nmap",
            }
            <= command_callbacks.keys()
        )
        expected_adapters = {
            "recon": telegram_bot.recon_command,
            "webscan": telegram_bot.web_command,
            "web": telegram_bot.web_command,
            "crack": telegram_bot.crack_command,
            "payload": telegram_bot.payload_command,
            "osint": telegram_bot.osint_command,
            "nmap": telegram_bot.nmap_shortcut,
        }
        for command, adapter in expected_adapters.items():
            with self.subTest(command=command):
                self.assertIs(command_callbacks[command], adapter)
        callbacks = {handler.callback for handler in fake_app.handlers}
        self.assertIn(telegram_bot.handle_photo, callbacks)
        self.assertIn(telegram_bot.handle_voice, callbacks)
        self.assertIsNotNone(getattr(telegram_bot, "handle_document", None))
        self.assertIn(telegram_bot.handle_document, callbacks)


    # ─── Task ownership tests ───

    async def test_web_recon_submission_includes_user_id(self):
        update = make_text_update("example.com:8080/a")
        update.message.reply_text.return_value = Mock(name="ack")
        telegram_bot._new_wizard(
            7,
            "web",
            70,
            step="awaiting_target",
            audit_type="recon",
        )
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.target_engine, "set_target"),
            patch.object(telegram_bot.task_queue, "submit", return_value="W-1") as submit,
            patch.object(telegram_bot.audit_log, "log"),
            patch.object(telegram_bot, "_poll_playbook_task", new=Mock(return_value=None)),
            patch.object(asyncio, "create_task"),
        ):
            await telegram_bot.handle_text(update, None)

        params = submit.call_args[0][2]
        self.assertIn("user_id", params)
        self.assertEqual(params["user_id"], 7)

    async def test_web_audit_submission_includes_user_id(self):
        update = make_text_update("example.com:8080/a")
        update.message.reply_text.return_value = Mock(name="ack")
        telegram_bot._new_wizard(
            7,
            "web",
            70,
            step="awaiting_target",
            audit_type="vuln",
        )
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.target_engine, "set_target"),
            patch.object(telegram_bot.task_queue, "submit", return_value="W-1") as submit,
            patch.object(telegram_bot.audit_log, "log"),
            patch.object(telegram_bot, "_poll_playbook_task", new=Mock(return_value=None)),
            patch.object(asyncio, "create_task"),
        ):
            await telegram_bot.handle_text(update, None)

        params = submit.call_args[0][2]
        self.assertIn("user_id", params)
        self.assertEqual(params["user_id"], 7)

    async def test_osint_domain_submission_includes_user_id(self):
        update = make_text_update("example.com")
        update.message.reply_text.return_value = Mock(name="ack")
        telegram_bot._new_wizard(
            7,
            "osint",
            70,
            step="awaiting_target",
            osint_type="domain",
        )
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.target_engine, "set_target"),
            patch.object(telegram_bot.task_queue, "submit", return_value="O-1") as submit,
            patch.object(telegram_bot.audit_log, "log"),
            patch.object(telegram_bot, "_poll_playbook_task", new=Mock(return_value=None)),
            patch.object(asyncio, "create_task"),
        ):
            await telegram_bot.handle_text(update, None)

        params = submit.call_args[0][2]
        self.assertIn("user_id", params)
        self.assertEqual(params["user_id"], 7)

    async def test_tarea_command_passes_uid_to_queue(self):
        update = make_text_update("/tarea ABC123")
        context = SimpleNamespace(args=["ABC123"])
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(
                telegram_bot.task_queue, "get_status", return_value={"error": "Tarea no encontrada"}
            ) as gs,
        ):
            await telegram_bot.tarea(update, context)
        gs.assert_called_once_with("ABC123", user_id=7)

    async def test_tareas_command_passes_uid_to_queue(self):
        update = make_text_update("/tareas")
        context = SimpleNamespace(args=[])
        list_tasks = Mock(return_value=[])
        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot.task_queue, "list_tasks", new=list_tasks) as lt,
        ):
            await telegram_bot.tareas(update, context)
        lt.assert_called_once_with(user_id=7)

    async def test_voice_handler_delegates_blocking_ops_to_thread(self):
        update = make_text_update("unused")
        voice = Mock()
        voice.get_file = AsyncMock()
        file = AsyncMock()
        file.download_as_bytearray = AsyncMock(return_value=b"mock_ogg")
        voice.get_file.return_value = file
        update.message.voice = voice
        update.message.reply_text = AsyncMock()

        def capture_thread_call(func, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(
                asyncio, "to_thread", side_effect=capture_thread_call
            ) as to_thread,
            patch.object(telegram_bot.Path, "write_bytes"),
            patch.object(telegram_bot.subprocess, "run"),
            patch.object(telegram_bot.Path, "with_suffix", return_value=Mock()),
            patch.object(telegram_bot.Path, "exists", return_value=True),
            patch.object(telegram_bot.Path, "unlink"),
            patch("builtins.open", unittest.mock.mock_open()),
        ):
            await telegram_bot.handle_voice(update, None)

        self.assertTrue(to_thread.called, "asyncio.to_thread was not called")


    # ─── Task 12: Transactional wizard transitions ───

    async def test_recon_type_delivery_failure_does_not_mutate_state(self):
        wizard = telegram_bot._new_wizard(7, "recon", 70)
        original = dict(wizard)
        _, query = make_callback_update("unused")
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with self.assertRaises(BadRequest):
            await telegram_bot._handle_recon_type(query, 7, wizard, "quick")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        self.assertEqual(wizard["step"], "select_type")

    async def test_web_type_delivery_failure_does_not_mutate_state(self):
        wizard = telegram_bot._new_wizard(7, "web", 70)
        original = dict(wizard)
        _, query = make_callback_update("unused")
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with self.assertRaises(BadRequest):
            await telegram_bot._handle_web_type(query, 7, wizard, "vuln")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        self.assertEqual(wizard["step"], "select_type")

    async def test_red_type_delivery_failure_does_not_mutate_state(self):
        wizard = telegram_bot._new_wizard(7, "red", 70)
        original = dict(wizard)
        _, query = make_callback_update("unused")
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with self.assertRaises(BadRequest):
            await telegram_bot._handle_red_type(query, 7, wizard, "quick")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        self.assertEqual(wizard["step"], "select_type")

    async def test_osint_type_delivery_failure_does_not_mutate_state(self):
        wizard = telegram_bot._new_wizard(7, "osint", 70)
        original = dict(wizard)
        _, query = make_callback_update("unused")
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with self.assertRaises(BadRequest):
            await telegram_bot._handle_osint_type(query, 7, wizard, "email")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        self.assertEqual(wizard["step"], "select_type")

    async def test_crack_type_delivery_failure_does_not_mutate_state(self):
        wizard = telegram_bot._new_wizard(7, "crack", 70)
        original = dict(wizard)
        _, query = make_callback_update("unused")
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with self.assertRaises(BadRequest):
            await telegram_bot._handle_crack_type(query, 7, wizard, "hash")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        self.assertEqual(wizard["step"], "select_type")

    async def test_payload_type_delivery_failure_does_not_mutate_state(self):
        wizard = telegram_bot._new_wizard(7, "payload", 70)
        original = dict(wizard)
        _, query = make_callback_update("unused")
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with self.assertRaises(BadRequest):
            await telegram_bot._handle_payload_type(query, 7, wizard, "reverse")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        self.assertEqual(wizard["step"], "select_type")

    async def test_crack_value_delivery_failure_does_not_mutate_state(self):
        telegram_bot._new_wizard(
            7, "crack", 70, step="awaiting_value", crack_type="hash"
        )
        _, query = make_callback_update("unused")
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with self.assertRaises(BadRequest):
            await telegram_bot._handle_crack_value(
                query, 7, "5d41402abc4b2a76b9719d911017c592"
            )

        wizard = telegram_bot.user_wizards[7]
        self.assertIsNotNone(wizard)
        self.assertEqual(wizard["step"], "awaiting_value")

    async def test_reverse_lang_delivery_failure_does_not_mutate_state(self):
        wizard = telegram_bot._new_wizard(
            7, "payload", 70, step="select_lang", payload_type="reverse"
        )
        original = dict(wizard)
        _, query = make_callback_update("unused")
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with self.assertRaises(BadRequest):
            await telegram_bot._handle_payload_lang(query, 7, wizard, "bash")

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard, original)
        self.assertEqual(wizard["step"], "select_lang")

    async def test_custom_dict_method_delivery_failure_does_not_mutate(self):
        wizard = telegram_bot._new_wizard(
            7, "crack", 70, step="select_dict", crack_type="hash",
            target="5d41402abc4b2a76b9719d911017c592", algorithm="MD5",
        )
        original = dict(wizard)
        data = telegram_bot._wizard_callback(wizard, "method", "custom")
        update, query = make_callback_update(data)
        query.edit_message_text.side_effect = BadRequest("Delivery failed")

        with (
            patch.object(telegram_bot, "_check_role", return_value=True),
            patch.object(telegram_bot, "_rate_limit_msg", return_value=None),
            patch.object(telegram_bot.hacking.crypto, "hash_crack") as hash_crack,
        ):
            with self.assertRaises(BadRequest):
                await telegram_bot.handle_callback(update, None)

        self.assertIs(wizard, telegram_bot.user_wizards[7])
        self.assertEqual(wizard["step"], "select_dict")
        self.assertNotIn("awaiting_dictionary", wizard["step"])
        hash_crack.assert_not_called()

    # ─── Task 12: Honest OSINT failures ───

    def test_email_osint_dns_noanswer_is_ok(self):
        import dns.resolver
        mock_resolve = Mock(side_effect=dns.resolver.NoAnswer)
        mock_fetch = Mock(return_value=[{"name_value": "www.example.com"}])

        with (
            patch.object(dns.resolver, "resolve", mock_resolve),
            patch.object(telegram_bot.hacking.osint, "_fetch_json", mock_fetch),
        ):
            result = telegram_bot.hacking.osint.email_osint("user@example.com")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mx_records"], [])
        self.assertFalse(result.get("warnings"))

    def test_email_osint_dns_resolver_failure_is_partial(self):
        import dns.resolver
        mock_resolve = Mock(side_effect=TimeoutError("DNS timeout"))
        mock_fetch = Mock(return_value=[{"name_value": "www.example.com"}])

        with (
            patch.object(dns.resolver, "resolve", mock_resolve),
            patch.object(telegram_bot.hacking.osint, "_fetch_json", mock_fetch),
        ):
            result = telegram_bot.hacking.osint.email_osint("user@example.com")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["mx_records"], [])
        self.assertIn("warnings", result)

    def test_email_osint_http_failure_is_partial(self):
        import dns.resolver
        mx_entry = SimpleNamespace(exchange="mx1.example.com.")
        mock_resolve = Mock(return_value=[mx_entry])
        mock_fetch = Mock(return_value={"error": "HTTP 500"})

        with (
            patch.object(dns.resolver, "resolve", mock_resolve),
            patch.object(telegram_bot.hacking.osint, "_fetch_json", mock_fetch),
        ):
            result = telegram_bot.hacking.osint.email_osint("user@example.com")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["mx_records"], ["mx1.example.com."])
        self.assertIn("warnings", result)

    def test_email_osint_all_ok(self):
        import dns.resolver
        mx_entry = SimpleNamespace(exchange="mx1.example.com.")
        mock_resolve = Mock(return_value=[mx_entry])
        mock_fetch = Mock(return_value=[{"name_value": "www.example.com"}])

        with (
            patch.object(dns.resolver, "resolve", mock_resolve),
            patch.object(telegram_bot.hacking.osint, "_fetch_json", mock_fetch),
        ):
            result = telegram_bot.hacking.osint.email_osint("user@example.com")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mx_records"], ["mx1.example.com."])
        self.assertFalse(result.get("warnings"))

    def test_email_osint_all_failed_is_error(self):
        import dns.resolver
        mock_resolve = Mock(side_effect=TimeoutError("DNS timeout"))
        mock_fetch = Mock(return_value={"error": "HTTP 500"})

        with (
            patch.object(dns.resolver, "resolve", mock_resolve),
            patch.object(telegram_bot.hacking.osint, "_fetch_json", mock_fetch),
        ):
            result = telegram_bot.hacking.osint.email_osint("user@example.com")

        self.assertEqual(result["status"], "error")
        self.assertIn("warnings", result)

    # ─── Task 12: OSINT domain poller audit ───

    async def test_osint_domain_poller_audits_completion_as_success(self):
        """OSINT domain playbook completion audits 'ok' based on actual outcome."""
        audit_mock = Mock()
        message = SimpleNamespace(edit_text=AsyncMock(), reply_text=AsyncMock())
        completed = {
            "status": "completed",
            "target": "example.com",
            "params": {"playbook": "osint_domain", "depth": "normal", "user_id": 7},
            "result": {
                "summary": "Playbook completado",
                "results": [{"step_id": "dns", "label": "DNS", "success": True}],
            },
        }

        with (
            patch.object(telegram_bot.task_queue, "get_status", return_value=completed),
            patch.object(asyncio, "sleep", new=AsyncMock()),
            patch.object(telegram_bot.audit_log, "log", audit_mock),
        ):
            await telegram_bot._poll_playbook_task(
                message, "OSINT-1", "OSINT de Dominio",
                return_to_menu=True, uid=7,
            )

        audit_mock.assert_called_once()
        args = audit_mock.call_args
        self.assertEqual(args[0][2], "wizard:osint")
        self.assertEqual(args[0][4], "ok")

    async def test_osint_domain_poller_audits_failure(self):
        """OSINT domain playbook failure audits 'error' based on actual outcome."""
        audit_mock = Mock()
        message = SimpleNamespace(edit_text=AsyncMock(), reply_text=AsyncMock())
        failed = {
            "status": "failed",
            "target": "example.com",
            "params": {"playbook": "osint_domain", "depth": "normal", "user_id": 7},
            "error": "Todos los pasos del playbook fallaron",
        }

        with (
            patch.object(telegram_bot.task_queue, "get_status", return_value=failed),
            patch.object(asyncio, "sleep", new=AsyncMock()),
            patch.object(telegram_bot.audit_log, "log", audit_mock),
        ):
            await telegram_bot._poll_playbook_task(
                message, "OSINT-FAIL", "OSINT de Dominio",
                return_to_menu=True, uid=7,
            )

        audit_mock.assert_called_once()
        args = audit_mock.call_args
        self.assertEqual(args[0][2], "wizard:osint")
        self.assertIn(args[0][4], ("error", "partial"))


if __name__ == "__main__":
    unittest.main()
