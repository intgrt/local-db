# Local-First Data Management
## Running Local Databases via a CLI and a Local LLM

## What It Is

A locally-run task management system. There is no cloud service, no external API, and no web interface. Everything runs on the local machine.

---

## Components

### SQLite Database (`tasks.db`)

The single source of truth. Stores all tasks in a table called `ActionList` with the following fields:

| Field | Description |
|---|---|
| ItemID | Auto-assigned unique ID |
| Project | Groups tasks by project (e.g. Integrate) |
| Who | Owner initials (max 5 chars) |
| Status | One of: Open, IP, Wait, Done, Deferred |
| Priority | 1 (low) to 5 (high) |
| Action | The task description |
| Notes | Supporting detail |

SQLite is a file-based database — no server process required. The database file can be copied, backed up, or opened directly with any SQLite tool.

---

### Interactive CLI (`tasks_cli_interactive.py`)

A Python script providing a menu-driven terminal interface for searching and adding tasks. It connects directly to the SQLite database using Python's built-in `sqlite3` library.

Key behaviours:
- **Search** — full-text search across Project, Action, Notes, and Who fields
- **Add** — guided prompts to create a new task with project, owner, status, priority, and notes
- **Clipboard summarisation** — if clipboard content is present when adding a task, it can be passed to the LLM to generate a title and notes automatically

---

### Local LLM via Ollama (`qwen3:8b`)

Ollama runs a large language model locally — in this case `qwen3:8b`. The LLM is not involved in search or storage. Its sole role is **summarisation at task creation time**: when the user has copied text (e.g. from a browser or document), the LLM reads it and returns a structured JSON object containing a suggested task title and notes.

The Python code sends the clipboard text to Ollama via a subprocess call and parses the JSON response. The user can accept or override the suggestion before anything is written to the database.

The LLM has no persistent memory and no access to the database — it only sees the text passed to it in that moment.

---

## Data Flow

```
User input
    │
    ▼
tasks_cli_interactive.py
    │
    ├── Search query ──────────────► SQLite (tasks.db) ──► results displayed
    │
    └── Add task
            │
            ├── Manual entry ──────► SQLite (tasks.db)
            │
            └── Clipboard text
                    │
                    ▼
                Ollama (qwen3:8b)
                    │
                    ▼
              Suggested title + notes
                    │
                    ▼
              User accepts/edits
                    │
                    ▼
                SQLite (tasks.db)
```

---

## Structured Output Contract

When the LLM is used for clipboard summarisation, it is not treated as a free-form text generator. It is given an explicit output contract: return JSON in a specific shape with specific field types. The required schema is:

```json
{
  "title": "string (max 80 chars)",
  "summary": "string (max 3 sentences)",
  "bullets": ["string", "string", "..."]
}
```

After the LLM responds, the code validates the output against this contract before using it — checking that all required fields are present, non-empty, and correctly typed. If validation fails, the error is sent back to the model in a follow-up prompt asking it to correct the response. This retry loop runs up to three times before giving up.

---

## Why Local

- No subscription or API cost
- Data stays on the machine
- Works without an internet connection
- The LLM model (`qwen3:8b`) runs entirely in RAM via Ollama
