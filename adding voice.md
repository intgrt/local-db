You already have a clean “local-first” core: **SQLite (`tasks.db`) + Python CLI + optional local LLM summarization via Ollama**. A voice interface can be added as a **thin input layer** that converts speech → text → the same “Add/Search/Update” operations your CLI already performs.

## What to add (minimal surface area)

### 1) A new wrapper entrypoint: `tasks_voice.py`

This script should do only four things:

1. capture audio (push-to-talk or VAD)
2. run offline STT locally
3. parse the transcript into a structured command
4. call your existing SQLite write/search functions (or invoke the same CLI module)

This keeps your current system unchanged: **SQLite remains the single source of truth**.

### 2) Speech-to-text engine (offline)

Pick one of these practical offline options:

- **faster-whisper** (GPU-friendly, good accuracy)
- **whisper.cpp** (single binary, quantized models, very deployable)

Either one is a drop-in “speech → text” component; nothing else in your architecture needs to change.

### 3) Command parsing (avoid a “research project”)

Use a **small fixed command grammar** at first. Do not use an LLM for intent parsing unless you must.

Example supported utterances:

- **Add:** “add task …”, “new task …”
- **Search:** “search …”, “find …”
- **Update:** “set item 12 status to done”, “change task 12 priority to 4”
- **Notes:** “add note to item 12 …”

These map directly onto your `ActionList` fields (Project, Who, Status, Priority, Action, Notes).

### 4) Reuse your existing “clipboard summarization” pattern (optional)

Your existing design uses the local LLM only during task creation and enforces a JSON contract.
You can keep that exact pattern and optionally extend it:

- Voice command: “add task from clipboard”
- Then your current flow kicks in: clipboard → Ollama (`qwen3:8b`) → validated JSON → user confirm → SQLite write.

That avoids trying to make the LLM “understand everything said.”

------

## Recommended “thin” voice UX

To keep it reliable and fast to ship:

- **Push-to-talk** hotkey → record until release → transcribe → execute → speak/print confirmation
  (Push-to-talk dramatically reduces false triggers vs always-on.)
- After executing, read back a confirmation like:
  - “Added item 57, project Integrate, status Open, priority 3.”
  - “Updated item 12 status to Done.”

------

## Implementation shape (so you don’t rewrite your CLI)

Refactor (or wrap) your current Python code into these reusable functions:

- `search_tasks(query: str) -> list[rows]`
- `add_task(project, who, status, priority, action, notes) -> item_id`
- `update_task(item_id, fields: dict) -> None`

Then:

- `tasks_cli_interactive.py` calls those functions (as it does now, just via imports)
- `tasks_voice.py` calls the same functions after parsing speech

This preserves your current data flow and keeps voice as just another input channel.

------

## If you want Firebase later

Keep it as a **replication layer** (not part of voice). Voice updates SQLite; a separate sync process mirrors to Firebase when online. This maintains “SQLite is source of truth” as documented.

------

If you paste (or upload) your current `tasks_cli_interactive.py` (or at least the functions that write/update SQLite), I can give you a concrete `tasks_voice.py` skeleton that calls into it without changing your schema.