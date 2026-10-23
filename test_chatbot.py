"""Automated tests for Nova. Run: python -m unittest -v."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from assistant import LocalAssistant, safe_calculate


class CalculatorTests(unittest.TestCase):
    def test_precedence_and_parentheses(self):
        self.assertEqual(safe_calculate("2 + 3 * (4 - 1)"), 11)

    def test_division(self):
        self.assertEqual(safe_calculate("10 / 4"), 2.5)

    def test_rejects_function_calls(self):
        with self.assertRaises(ValueError):
            safe_calculate("__import__('os').system('echo unsafe')")

    def test_rejects_names(self):
        with self.assertRaises(ValueError):
            safe_calculate("secret + 1")

    def test_division_by_zero(self):
        with self.assertRaises(ValueError):
            safe_calculate("5 / 0")

    def test_rejects_huge_exponent(self):
        with self.assertRaises(ValueError):
            safe_calculate("2 ** 100")


    def test_rejects_arbitrarily_large_integer_cleanly(self):
        with self.assertRaises(ValueError):
            safe_calculate("9" * 500)

    def test_rejects_infinite_float_literal(self):
        with self.assertRaises(ValueError):
            safe_calculate("1e999")


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temp_dir.name) / "assistant.json"
        self.fixed_time = datetime(2026, 10, 23, 18, 30, 0)
        self.bot = LocalAssistant(self.data_file, clock=lambda: self.fixed_time)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_greeting_and_help(self):
        self.assertIn("Hello", self.bot.process("hello"))
        self.assertIn("/todo add", self.bot.process("/help"))

    def test_calculator_command(self):
        self.assertIn("Result: 14", self.bot.process("/calc 2 + 3 * 4"))

    def test_name_persists(self):
        self.bot.process("/name Pappu")
        other = LocalAssistant(self.data_file, clock=lambda: self.fixed_time)
        self.assertIn("Pappu", other.process("what is my name"))

    def test_todo_add_list_done(self):
        self.assertIn("#1", self.bot.process("/todo add Finish project"))
        self.assertIn("Finish project", self.bot.process("/todo list"))
        self.assertIn("complete", self.bot.process("/todo done 1"))

    def test_note_add_search_delete(self):
        self.bot.process("/note add Study | Revise Python")
        self.assertIn("Revise Python", self.bot.process("/note search Python"))
        self.assertIn("Deleted", self.bot.process("/note delete 1"))

    def test_note_requires_separator(self):
        self.assertIn("Usage", self.bot.process("/note add Missing separator"))

    def test_time_and_date(self):
        self.assertIn("06:30:00 PM", self.bot.process("/time"))
        self.assertIn("Friday, 23 October 2026", self.bot.process("/date"))

    def test_long_input(self):
        self.assertIn("too long", self.bot.process("x" * 1001))

    def test_blank_input(self):
        self.assertIn("/help", self.bot.process("   "))


    def test_invalid_saved_entries_are_ignored_safely(self):
        self.data_file.write_text(json.dumps({
            "nickname": 123,
            "todos": ["invalid", {"id": "not-an-int", "text": "bad", "done": False}],
            "notes": ["invalid", {"id": 1, "title": "", "body": "bad"}],
        }), encoding="utf-8")
        bot = LocalAssistant(self.data_file, clock=lambda: self.fixed_time)
        self.assertIn("invalid saved entries", bot.storage.load_warning)
        self.assertIn("empty", bot.process("/todo list"))
        self.assertIn("No notes", bot.process("/note list"))

if __name__ == "__main__":
    unittest.main()
