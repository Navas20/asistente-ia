import asyncio
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import telegram_bot


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


class TestMenuButtons(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        telegram_bot.user_wizards.clear()
        telegram_bot.target_engine.get_target = Mock(return_value=None)
        telegram_bot.target_engine.get_context_summary = Mock(return_value="")
        telegram_bot.audit_log.log = Mock()
        telegram_bot.task_queue.submit = Mock(return_value="test_task_id")
        telegram_bot.task_queue.get_status = Mock(return_value={"status": "completed", "result": {}})
        telegram_bot.tools_engine.tools_engine.run_tool = Mock(return_value=SimpleNamespace(success=True, stdout="ok", stderr="", error="", elapsed=1.0))

    async def test_menu_recon(self):
        update = make_text_update("\U0001f50d Recon")
        await telegram_bot.handle_text(update, None)
        self.assertIn(7, telegram_bot.user_wizards)
        self.assertEqual(telegram_bot.user_wizards[7]["type"], "recon")

    async def test_menu_web(self):
        update = make_text_update("\U0001f310 Web")
        await telegram_bot.handle_text(update, None)
        self.assertIn(7, telegram_bot.user_wizards)
        self.assertEqual(telegram_bot.user_wizards[7]["type"], "web")

    async def test_menu_crack(self):
        update = make_text_update("\U0001f511 Crack")
        await telegram_bot.handle_text(update, None)
        self.assertIn(7, telegram_bot.user_wizards)
        self.assertEqual(telegram_bot.user_wizards[7]["type"], "crack")

    async def test_menu_payloads(self):
        update = make_text_update("\U0001f4a3 Payloads")
        await telegram_bot.handle_text(update, None)
        self.assertIn(7, telegram_bot.user_wizards)
        self.assertEqual(telegram_bot.user_wizards[7]["type"], "payload")

    async def test_menu_red(self):
        update = make_text_update("\U0001f4e1 Red")
        await telegram_bot.handle_text(update, None)
        self.assertIn(7, telegram_bot.user_wizards)
        self.assertEqual(telegram_bot.user_wizards[7]["type"], "red")

    async def test_menu_osint(self):
        update = make_text_update("\U0001f50e OSINT")
        await telegram_bot.handle_text(update, None)
        self.assertIn(7, telegram_bot.user_wizards)
        self.assertEqual(telegram_bot.user_wizards[7]["type"], "osint")

    async def test_menu_objetivo(self):
        update = make_text_update("\u2699\ufe0f Objetivo")
        await telegram_bot.handle_text(update, None)
        self.assertIn(7, telegram_bot.user_wizards)
        self.assertEqual(telegram_bot.user_wizards[7]["type"], "objetivo")
        self.assertEqual(telegram_bot.user_wizards[7]["step"], "awaiting_target")


class TestCallbackRouting(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        telegram_bot.user_wizards.clear()
        telegram_bot.target_engine.get_target = Mock(return_value=None)
        telegram_bot.audit_log.log = Mock()

    def test_callback_handler_keys(self):
        expected = [
            "recon_quick", "recon_normal", "recon_full",
            "web_nikto", "web_sqli", "web_ssl", "web_crawler",
            "crack_hash", "crack_dict_integrated", "crack_dict_custom",
            "payload_reverse", "payload_meterpreter", "payload_webshell",
            "payload_lang_bash", "payload_lang_python", "payload_lang_php",
            "payload_lang_powershell", "payload_lang_asp", "payload_lang_aspx",
            "payload_lang_jsp", "payload_lang_py",
            "red_wifi_scan", "red_wifi_crack", "red_lan_scan",
            "osint_email", "osint_domain", "osint_person",
        ]
        for key in expected:
            self.assertIn(key, telegram_bot._CALLBACK_HANDLERS, f"Missing handler: {key}")

    async def test_cancel_callback(self):
        telegram_bot.user_wizards[7] = {"type": "recon", "step": "select_type", "data": {}}
        update, query = make_callback_update("cancel")
        await telegram_bot.handle_callback(update, None)
        query.answer.assert_awaited_once()
        self.assertNotIn(7, telegram_bot.user_wizards)

    async def test_back_callback(self):
        telegram_bot.user_wizards[7] = {"type": "recon", "step": "select_type", "data": {}}
        update, query = make_callback_update("back_recon")
        await telegram_bot.handle_callback(update, None)
        query.answer.assert_awaited_once()
        self.assertNotIn(7, telegram_bot.user_wizards)


class TestCrackHashValidation(unittest.TestCase):
    def test_md5_detected(self):
        h = "5d41402abc4b2a76b9719d911017c592"
        algo, error = telegram_bot._validate_hash_algorithm(h)
        self.assertEqual(algo, "MD5")
        self.assertIsNone(error)

    def test_sha1_detected(self):
        h = "a94a8fe5ccb19ba61c4c0873d391e987982fbbd3"
        algo, error = telegram_bot._validate_hash_algorithm(h)
        self.assertEqual(algo, "SHA1")
        self.assertIsNone(error)

    def test_sha256_detected(self):
        h = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        algo, error = telegram_bot._validate_hash_algorithm(h)
        self.assertEqual(algo, "SHA256")
        self.assertIsNone(error)

    def test_invalid_hash(self):
        algo, error = telegram_bot._validate_hash_algorithm("notahash")
        self.assertIsNone(algo)
        self.assertIsNotNone(error)

    def test_invalid_string(self):
        algo, error = telegram_bot._validate_hash_algorithm("")
        self.assertIsNone(algo)
        self.assertIsNotNone(error)

    def test_mixed_case_md5(self):
        h = "5D41402ABC4B2A76B9719D911017C592"
        algo, error = telegram_bot._validate_hash_algorithm(h)
        self.assertEqual(algo, "MD5")
        self.assertIsNone(error)


class TestEndpointParsing(unittest.TestCase):
    def test_ipv4_valid(self):
        ip, port, error = telegram_bot._parse_endpoint("192.168.1.1:8080")
        self.assertEqual(ip, "192.168.1.1")
        self.assertEqual(port, 8080)
        self.assertIsNone(error)

    def test_ipv6_valid(self):
        ip, port, error = telegram_bot._parse_endpoint("[::1]:4444")
        self.assertEqual(ip, "::1")
        self.assertEqual(port, 4444)
        self.assertIsNone(error)

    def test_invalid_port(self):
        _, _, error = telegram_bot._parse_endpoint("1.2.3.4:99999")
        self.assertIsNotNone(error)

    def test_missing_port(self):
        _, _, error = telegram_bot._parse_endpoint("1.2.3.4")
        self.assertIsNotNone(error)

    def test_empty_string(self):
        _, _, error = telegram_bot._parse_endpoint("")
        self.assertIsNotNone(error)


class TestMainKeyboard(unittest.TestCase):
    def test_main_keyboard_defined(self):
        kb = telegram_bot.MAIN_KEYBOARD
        self.assertIsInstance(kb, ReplyKeyboardMarkup)
        self.assertTrue(kb.resize_keyboard)

    def test_main_keyboard_buttons(self):
        kb = telegram_bot.MAIN_KEYBOARD
        buttons = [b.text for row in kb.keyboard for b in row]
        expected = ["\U0001f50d Recon", "\U0001f310 Web", "\U0001f511 Crack",
                     "\U0001f4a3 Payloads", "\U0001f4e1 Red", "\U0001f50e OSINT",
                     "\U0001f4cb Mis Tareas", "\u2753 Ayuda", "\u2699\ufe0f Objetivo"]
        for b in expected:
            self.assertIn(b, buttons)


if __name__ == "__main__":
    unittest.main()
