# Local Task List

A local-first task management system with a menu-driven CLI and a Flask web UI. Stores data in a SQLite database. Runs entirely offline. No cloud services or external APIs required.

## Stack

- Python 3.x
- SQLite (`tasks.db`)
- Flask (`tasks_web.py`) — web UI, runs on `http://localhost:5000`
- Ollama (`qwen3:8b`) — optional, used for clipboard summarization
- `pyperclip` — optional, required for clipboard access

## Database

**File:** `tasks.db`
**Table:** `ActionList`

| Column   | Type      | Constraints                                         |
|----------|-----------|-----------------------------------------------------|
| ItemID   | INTEGER   | PRIMARY KEY AUTOINCREMENT                           |
| Project  | TEXT      |                                                     |
| Who      | CHAR(5)   | Max 5 characters                                    |
| Status   | TEXT      | Open \| IP \| Wait \| Done \| Deferred              |
| Priority | INTEGER   | 1–5                                                 |
| Action   | TEXT      | Task title                                          |
| Notes    | TEXT      |                                                     |

## Usage

```
python tasks_cli_interactive.py
```

**Main menu options:**

| Input       | Action                          |
|-------------|---------------------------------|
| `1`         | Search (prompts for term)       |
| `1 <term>`  | Search with inline term         |
| `2`         | Add new task                    |
| `3`         | Quit                            |

### Search

Full-text search across Project, Action, Notes, and Who fields. Returns up to 50 results sorted by status (Open → IP → Wait → Done) then priority. Enter an ItemID from results to view full detail.

### Add Task

Prompts for Project, Who, Status, Priority, Title, and Notes. If `pyperclip` is installed, optionally reads clipboard content and sends it to Ollama (`qwen3:8b`) for summarization. The model returns a structured JSON response (`title`, `summary`, `bullets`) which populates the Title and Notes fields. The user reviews and confirms before writing to the database.

LLM output is validated against a strict schema with up to 3 retry attempts on failure.

## Web UI

```
pip install flask
python tasks_web.py
```

Runs at `http://localhost:5000`.

| Route | Function |
|---|---|
| `/` | Task list — filter by Project/Who, sort by any column, edit, delete |
| `/add` | Add task form |
| `/edit/<id>` | Edit existing task |
| `/delete/<id>` | Delete task |
| `/reports` | Tasks by Project × Status pivot table, filterable by Who |

## Requirements

- Python 3.x
- Flask (`pip install flask`) — required for web UI
- Ollama running locally with `qwen3:8b` pulled (only required for clipboard summarization)
- `pyperclip` installed (only required for clipboard access)

## Platform

Windows. CMD window color and title are set at runtime.
