# Nova — Python Chat Assistant

Nova is a feature-rich, local-first command-line assistant built with Python's standard library.

This is a deterministic, rule-based assistant—not a cloud LLM. It works without an API key, paid service, or third-party package.

## Features
- Friendly chat with simple intent matching and remembered preferred name
- Safe arithmetic calculator based on Python's AST parser (never eval)
- Persistent task manager: add, list, complete, and delete tasks
- Persistent notes: add, list, search, and delete notes
- Local date/time, profile, help, and session statistics
- Export the current conversation to a text file
- JSON persistence with atomic writes
- Input limits, friendly error messages, and automated tests
- GitHub Actions workflow to run the test suite

## Requirements
Python 3.10 or newer recommended. No third-party packages.

## Run
\`\`\`bash
python chatbot.py
\`\`\`
On Windows, use \`py chatbot.py\`.

## Commands
| Command | Example | Purpose |
|---|---|---|
| Help | \`/help\` | Show supported commands |
| Calculator | \`/calc 2 + 3 * (4 - 1)\` | Calculate safely |
| Add task | \`/todo add Finish the project\` | Save a task |
| List tasks | \`/todo list\` | List tasks |
| Complete task | \`/todo done 1\` | Mark a task complete |
| Delete task | \`/todo delete 1\` | Delete a task |
| Add note | \`/note add Study plan | Revise Python loops\` | Save a titled note |
| List notes | \`/note list\` | List notes |
| Search notes | \`/note search Python\` | Search notes |
| Delete note | \`/note delete 1\` | Delete a note |
| Name | \`/name Pappu\` | Remember a preferred name |
| Profile | \`/profile\` | Show saved totals |
| Date/time | \`/date\`, \`/time\` | Show local date/time |
| Export | \`/export\` | Export this conversation |
| Quit | \`/quit\` | Exit |

Natural phrases supported include hello, how are you, who are you, and tell me a joke.

## Tests
Run \`python -m unittest -v\`. Tests cover calculator precedence, rejected unsafe expressions, notes, tasks, preferred-name persistence, date/time, and input validation.

## Data and privacy
Tasks and notes are stored in \`data/assistant_data.json\`. Conversation history remains in memory for the current session and can be exported with \`/export\`. Personal data and exports are excluded by \`.gitignore\`; never commit private notes or exports.

Nova does not browse the live web or call an online AI model. It clearly says when current information is unavailable.

## Project files
- \`chatbot.py\`: command-line entry point
- \`assistant.py\`: assistant logic, storage, and calculator
- \`test_chatbot.py\`: automated tests
- \`.github/workflows/tests.yml\`: test workflow
- \`.gitignore\`: excludes local data and Python cache
