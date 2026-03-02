# Local Task List

A local-first task management system with a menu-driven CLI and a Flask web UI. Stores data in a SQLite database. Runs entirely offline. No cloud services or external APIs required.

## Stack

- Python 3.x
- SQLite (`tasks.db`)
- Flask (`tasks_web.py`) — web UI, runs on `http://localhost:5000`
- Ollama (`qwen3:8b`) — optional, used for clipboard summarization
- `pyperclip` — optional, required for clipboard access

## File Structure

| File | Purpose |
|------|---------|
| `tasks_db.py` | Shared DB layer — constants, connection, all shared queries |
| `tasks_cli_interactive.py` | CLI entry point — menus, prompts, Ollama integration |
| `tasks_web.py` | Flask web UI entry point |
| `tasks.db` | SQLite database |

## Database

**File:** `tasks.db`
**Table:** `ActionList`

| Column   | Type      | Constraints                                      |
|----------|-----------|--------------------------------------------------|
| ItemID   | INTEGER   | PRIMARY KEY AUTOINCREMENT                        |
| Project  | TEXT      |                                                  |
| Who      | CHAR(5)   | Max 5 characters                                 |
| Status   | TEXT      | Open \| IP \| Wait \| Done \| Defrd \| Cncld    |
| Priority | INTEGER   | 1–5                                              |
| Action   | TEXT      | Task title                                       |
| Notes    | TEXT      |                                                  |

## CLI

**Launch:** `local-task-list-cli.bat`

**Main menu options:**

| Input       | Action                          |
|-------------|---------------------------------|
| `1`         | Search (prompts for term)       |
| `1 <term>`  | Search with inline term         |
| `2`         | Add new task                    |
| `3`         | Quit                            |

### Search

Full-text search across Project, Action, Notes, and Who fields. Results sorted by status (Open → IP → Wait → Defrd → Cncld → Done) then priority. Enter an ItemID from results to view full detail.

### Add Task

Prompts for Project, Who, Status, Priority, Title, and Notes. If `pyperclip` is installed, optionally reads clipboard content and sends it to Ollama (`qwen3:8b`) for summarization. The model returns a structured JSON response (`title`, `summary`, `bullets`) which populates the Title and Notes fields. The user reviews and confirms before writing to the database.

LLM output is validated against a strict schema with up to 3 retry attempts on failure.

## Web UI

**Launch:** `local-task-list-web.bat`

Runs at `http://localhost:5000`.

| Route | Function |
|---|---|
| `/` | Task list — filter, sort, search, print |
| `/add` | Add task form |
| `/edit/<id>` | Edit existing task |
| `/quick-update/<id>` | Inline field update from table view |
| `/delete/<id>` | Delete task |

### Task list features

- **Search** — full-text search across Project, Title, Notes, and Who; disables filter controls when active
- **Filter** by Project, User, and any combination of Status
- **Sort** by any column (ascending/descending)
- **Inline editing** — Who, Status, and Priority are editable directly in the table via dropdowns; page reloads and scrolls back to the edited row
- **Status colours** — each status has a distinct colour in the dropdown (blue=Open, orange=IP, grey=Wait, green=Done, silver=Defrd, purple=Cncld)
- **Resizable columns** — drag column header edge to resize
- **Print** — landscape layout, controls hidden, active filter summary shown in header

## Requirements

- Python 3.x
- Flask (`pip install flask`) — required for web UI
- Ollama running locally with `qwen3:8b` pulled — only required for clipboard summarization
- `pyperclip` — only required for clipboard access

## Platform

Windows. CMD window color and title are set at runtime.
