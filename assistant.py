"""Core logic for Nova, a local-first Python command-line assistant."""
from __future__ import annotations

import ast
import json
import math
import operator
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_ALLOWED_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_NUMBER = 1_000_000_000_000


def safe_calculate(expression: str) -> int | float:
    """Calculate arithmetic without eval(), imports, names, or function calls."""
    expression = expression.strip()
    if not expression or len(expression) > 120:
        raise ValueError("Enter an arithmetic expression of 1–120 characters.")
    try:
        root = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("That is not a valid arithmetic expression.") from exc

    node_count = 0

    def checked(value: Any) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Only numeric arithmetic is supported.")
        # Check integers directly: math.isfinite() can overflow when handed
        # an arbitrarily large Python integer parsed from user input.
        if isinstance(value, int):
            if abs(value) > _MAX_NUMBER:
                raise ValueError("Number or result is outside the supported range.")
            return value
        if not math.isfinite(value) or abs(value) > _MAX_NUMBER:
            raise ValueError("Number or result is outside the supported range.")
        return value

    def visit(node: ast.AST) -> int | float:
        nonlocal node_count
        node_count += 1
        if node_count > 40:
            raise ValueError("That expression is too complex.")
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return checked(node.value)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
            return checked(_ALLOWED_UNARY[type(node.op)](visit(node.operand)))
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent values must be between -8 and 8.")
            try:
                result = _ALLOWED_OPERATORS[type(node.op)](left, right)
            except ZeroDivisionError as exc:
                raise ValueError("Division by zero is not allowed.") from exc
            except (OverflowError, ValueError) as exc:
                raise ValueError("That calculation is outside the supported range.") from exc
            return checked(result)
        raise ValueError("Allowed operators: +, -, *, /, //, %, ** and parentheses.")
    return visit(root)


class AssistantStorage:
    """JSON-backed storage for tasks, notes, and a preferred name."""

    def __init__(self, file_path: str | Path | None = None):
        self.path = Path(file_path) if file_path else Path(__file__).resolve().parent / "data" / "assistant_data.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {"nickname": "", "todos": [], "notes": []}
        self.load_warning = ""
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("Data file must contain a JSON object.")

            nickname = loaded.get("nickname", "")
            if not isinstance(nickname, str):
                nickname = ""
            clean_todos = []
            clean_notes = []
            seen_todo_ids = set()
            seen_note_ids = set()
            dropped_items = False

            raw_todos = loaded.get("todos", [])
            if not isinstance(raw_todos, list):
                raw_todos = []
                dropped_items = True
            for item in raw_todos:
                if not isinstance(item, dict):
                    dropped_items = True
                    continue
                item_id, text, done = item.get("id"), item.get("text"), item.get("done", False)
                if (not isinstance(item_id, int) or isinstance(item_id, bool) or item_id < 1
                        or item_id in seen_todo_ids or not isinstance(text, str)
                        or not text.strip() or len(text) > 200 or not isinstance(done, bool)):
                    dropped_items = True
                    continue
                clean_todos.append({"id": item_id, "text": text, "done": done})
                seen_todo_ids.add(item_id)

            raw_notes = loaded.get("notes", [])
            if not isinstance(raw_notes, list):
                raw_notes = []
                dropped_items = True
            for item in raw_notes:
                if not isinstance(item, dict):
                    dropped_items = True
                    continue
                item_id, title, body = item.get("id"), item.get("title"), item.get("body")
                if (not isinstance(item_id, int) or isinstance(item_id, bool) or item_id < 1
                        or item_id in seen_note_ids or not isinstance(title, str)
                        or not title.strip() or len(title) > 100 or not isinstance(body, str)
                        or not body.strip() or len(body) > 2000):
                    dropped_items = True
                    continue
                clean_notes.append({"id": item_id, "title": title, "body": body})
                seen_note_ids.add(item_id)

            self.data = {"nickname": nickname[:40], "todos": clean_todos, "notes": clean_notes}
            if dropped_items:
                self.load_warning = "Some invalid saved entries were ignored; your original data file was left untouched."
        except (json.JSONDecodeError, OSError, ValueError):
            self.load_warning = "Saved data could not be read; the original file was left untouched."

    def save(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def next_id(self, section: str) -> int:
        return max((item.get("id", 0) for item in self.data[section] if isinstance(item, dict)), default=0) + 1


class LocalAssistant:
    """Deterministic offline assistant with commands and lightweight intent matching."""

    def __init__(self, storage_path: str | Path | None = None, clock: Callable[[], datetime] | None = None):
        self.storage = AssistantStorage(storage_path)
        self.clock = clock or datetime.now
        self.history: list[tuple[str, str]] = []
        self.turn_count = 0
        self.commands = {
            "/help": "Show available features",
            "/time": "Show current local time",
            "/date": "Show today's date",
            "/calc EXPR": "Calculate arithmetic safely",
            "/todo add TEXT": "Add a task",
            "/todo list": "List saved tasks",
            "/todo done ID": "Mark a task complete",
            "/todo delete ID": "Delete a task",
            "/note add TITLE | TEXT": "Save a note",
            "/note list": "List notes",
            "/note search WORD": "Search saved notes",
            "/note delete ID": "Delete a note",
            "/name NAME": "Save your preferred name",
            "/profile": "Show profile and saved totals",
            "/stats": "Show session message count",
            "/export": "Export this conversation",
            "/quit": "Exit the program",
        }

    def help_text(self) -> str:
        lines = ["Here is what I can do:", ""]
        lines.extend(f"  {cmd:<25} {description}" for cmd, description in self.commands.items())
        lines += ["", "You can also say hello, ask who I am, or ask for the date/time.",
                  "I work offline; live web answers are not available."]
        return "\n".join(lines)

    def process(self, message: str) -> str:
        message = str(message).strip()
        if not message:
            return "Send a message or type /help to see available features."
        if len(message) > 1000:
            return "That message is too long. Please keep it under 1,000 characters."
        try:
            reply = self._handle(message)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            reply = f"I couldn't complete that request: {exc}"
        except Exception:
            reply = "Something unexpected happened. Your session is still running; try /help."
        self.turn_count += 1
        self.history.extend([("You", message), ("Nova", reply)])
        return reply

    def _handle(self, message: str) -> str:
        if message.startswith("/"):
            return self._command(message)
        lowered = message.lower()
        match = re.fullmatch(r"(?:my name is|call me)\s+([\w .'-]{1,40})[.!]?", message, flags=re.I)
        if match:
            nickname = match.group(1).strip(" .'-")
            if not nickname:
                return "Tell me a name after 'my name is'."
            self.storage.data["nickname"] = nickname
            self.storage.save()
            return f"Nice to meet you, {nickname}! I'll remember that name on this device."
        if re.search(r"\b(what is|what's|tell me)\s+my name\b", lowered):
            name = self.storage.data.get("nickname", "")
            return f"You told me your name is {name}." if name else "You haven't set a name yet. Use /name YOUR_NAME."
        if re.search(r"\b(hello|hi|hey|good morning|good afternoon|good evening)\b", lowered):
            name = self.storage.data.get("nickname", "")
            return (f"Hello, {name}!" if name else "Hello!") + " I'm Nova, your local Python assistant. Type /help to explore."
        if re.search(r"\b(how are you|how's it going)\b", lowered):
            return "I'm running normally and ready to help. What would you like to do?"
        if re.search(r"\b(who are you|what are you|what can you do)\b", lowered):
            return "I'm Nova, a rule-based Python assistant. I can chat, calculate arithmetic, manage saved tasks and notes, and export this session. I don't use a remote AI model."
        if re.search(r"\b(what time is it|current time|tell me the time)\b", lowered):
            return f"The current local time is {self.clock().strftime('%I:%M:%S %p')}."
        if re.search(r"\b(today's date|what is the date|what's the date|current date)\b", lowered):
            return f"Today's date is {self.clock().strftime('%A, %d %B %Y')}."
        if re.search(r"\b(thank you|thanks|thx)\b", lowered):
            return "You're welcome! Happy to help."
        if re.search(r"\b(joke|make me laugh)\b", lowered):
            return "Why do programmers prefer dark mode? Because light attracts bugs."
        if re.search(r"\b(weather|live news|latest news|search the web)\b", lowered):
            return "I don't have live internet access in this project, so I can't verify current weather or news."
        if lowered in {"help", "commands", "menu"}:
            return self.help_text()
        if re.search(r"\b(i am sad|i feel sad|bad day|feeling low)\b", lowered):
            return "I'm sorry it's been a rough moment. Want to write down what's bothering you, or break a task into a smaller next step?"
        if re.search(r"\b(i am happy|great news|i did it)\b", lowered):
            return "That's great to hear! What helped you get there?"
        return "I'm not sure I understood that yet. Try rephrasing it, or type /help for the commands I support."

    def _command(self, message: str) -> str:
        first = message.split(maxsplit=1)
        command = first[0].lower()
        remainder = first[1].strip() if len(first) > 1 else ""
        if command == "/help":
            return self.help_text()
        if command == "/time":
            return f"Current local time: {self.clock().strftime('%I:%M:%S %p')}."
        if command == "/date":
            return f"Today: {self.clock().strftime('%A, %d %B %Y')}."
        if command == "/calc":
            if not remainder:
                return "Usage: /calc 12 * (3 + 2)"
            return f"Result: {safe_calculate(remainder):g}"
        if command == "/name":
            if not remainder:
                return "Usage: /name YOUR_NAME"
            name = remainder[:40]
            self.storage.data["nickname"] = name
            self.storage.save()
            return f"Got it. I'll call you {name} on this device."
        if command == "/profile":
            name = self.storage.data.get("nickname") or "Not set"
            opened = sum(not item.get("done", False) for item in self.storage.data["todos"])
            return f"Nova Local Assistant\nPreferred name: {name}\nOpen tasks: {opened}\nSaved notes: {len(self.storage.data['notes'])}\nSession turns: {self.turn_count}"
        if command == "/stats":
            return f"Session turns: {self.turn_count + 1}. Messages exchanged: {(self.turn_count + 1) * 2}."
        if command == "/todo":
            return self._todo(remainder)
        if command == "/note":
            return self._note(remainder)
        if command == "/export":
            return self._export()
        if command == "/quit":
            return "EXIT"
        return "Unknown command. Type /help to see supported commands."

    def _todo(self, text: str) -> str:
        parts = text.split(maxsplit=1)
        action = parts[0].lower() if parts else ""
        argument = parts[1].strip() if len(parts) > 1 else ""
        todos = self.storage.data["todos"]
        if action == "add":
            if not argument:
                return "Usage: /todo add Finish the project"
            if len(argument) > 200:
                return "Keep each task under 200 characters."
            item = {"id": self.storage.next_id("todos"), "text": argument, "done": False}
            todos.append(item)
            self.storage.save()
            return f"Added task #{item['id']}: {item['text']}"
        if action == "list":
            if not todos:
                return "Your task list is empty. Add one with /todo add TEXT."
            return "YOUR TASKS\n" + "\n".join(
                f"  #{item['id']} [{'x' if item.get('done') else ' '}] {item['text']}" for item in todos
            )
        if action in {"done", "delete"}:
            if not argument.isdigit():
                return f"Usage: /todo {action} ID"
            task_id = int(argument)
            item = next((entry for entry in todos if entry.get("id") == task_id), None)
            if item is None:
                return f"I couldn't find task #{task_id}."
            if action == "done":
                if item.get("done"):
                    return f"Task #{task_id} is already complete."
                item["done"] = True
                self.storage.save()
                return f"Marked task #{task_id} complete."
            todos.remove(item)
            self.storage.save()
            return f"Deleted task #{task_id}."
        return "Usage: /todo add TEXT | /todo list | /todo done ID | /todo delete ID"

    def _note(self, text: str) -> str:
        parts = text.split(maxsplit=1)
        action = parts[0].lower() if parts else ""
        argument = parts[1].strip() if len(parts) > 1 else ""
        notes = self.storage.data["notes"]
        if action == "add":
            if "|" not in argument:
                return "Usage: /note add TITLE | Your note text"
            title, body = (part.strip() for part in argument.split("|", 1))
            if not title or not body:
                return "Both a note title and note text are required."
            if len(title) > 100 or len(body) > 2000:
                return "Keep the title under 100 characters and note text under 2,000."
            note = {"id": self.storage.next_id("notes"), "title": title, "body": body}
            notes.append(note)
            self.storage.save()
            return f"Saved note #{note['id']}: {title}"
        if action == "list":
            if not notes:
                return "No notes saved yet. Use /note add TITLE | TEXT."
            return "SAVED NOTES\n" + "\n".join(
                f"  #{note['id']} {note['title']}: {note['body']}" for note in notes
            )
        if action == "search":
            if not argument:
                return "Usage: /note search keyword"
            matches = [n for n in notes if argument.casefold() in n["title"].casefold()
                       or argument.casefold() in n["body"].casefold()]
            if not matches:
                return "No matching notes found."
            return "MATCHING NOTES\n" + "\n".join(
                f"  #{n['id']} {n['title']}: {n['body']}" for n in matches
            )
        if action == "delete":
            if not argument.isdigit():
                return "Usage: /note delete ID"
            note_id = int(argument)
            note = next((entry for entry in notes if entry.get("id") == note_id), None)
            if note is None:
                return f"I couldn't find note #{note_id}."
            notes.remove(note)
            self.storage.save()
            return f"Deleted note #{note_id}."
        return "Usage: /note add TITLE | TEXT | /note list | /note search WORD | /note delete ID"

    def _export(self) -> str:
        if not self.history:
            return "There are no messages to export yet."
        export_dir = self.storage.path.parent / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        # Include microseconds so two exports in the same second never overwrite each other.
        filename = f"conversation_{self.clock().strftime('%Y%m%d_%H%M%S_%f')}.txt"
        destination = export_dir / filename
        lines = ["Nova Conversation Export", "=" * 24, ""]
        for speaker, text in self.history:
            lines.extend([f"{speaker}: {text}", ""])
        destination.write_text("\n".join(lines), encoding="utf-8")
        return f"Exported {self.turn_count} conversation turn(s) to: {destination}"
