import os
import sqlite3
import subprocess
import json
from pathlib import Path

try:
    import pyperclip
    HAS_CLIP = True
except Exception:
    HAS_CLIP = False

DB = r"D:\Datafiles5\softwarebuilds_other\Local_Task__List\tasks.db"
MODEL = "qwen3:8b"
ALLOWED_STATUS = ["Open", "IP", "Wait", "Done", "Deferred"]

# CMD cosmetics (Windows CMD)
CMD_COLOR = "B0"  # background=B (bright acqua), foreground=0 (black)


def set_cmd_ui(title: str):
    os.system(f"color {CMD_COLOR}")
    os.system(f'title {title}')


def db_connect():
    p = Path(DB)
    if not p.exists():
        raise SystemExit(f"DB not found: {p}")
    return sqlite3.connect(DB)


def ensure_project_column():
    con = db_connect()
    cur = con.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(ActionList)").fetchall()]
    if "Project" not in cols:
        cur.execute("ALTER TABLE ActionList ADD COLUMN Project TEXT;")
        con.commit()
    con.close()


def prompt(text, default=None, required=False):
    while True:
        suffix = f" [default: {default}]" if default is not None else ""
        val = input(f"{text}{suffix}: ").strip()
        if not val and default is not None:
            val = str(default)
        if required and not val:
            print("Required.")
            continue
        return val


def prompt_int(text, default=None, minv=None, maxv=None):
    while True:
        val = input(f"{text} [default: {default}]: ").strip()
        if not val and default is not None:
            return int(default)
        try:
            iv = int(val)
        except ValueError:
            print("Enter an integer.")
            continue
        if minv is not None and iv < minv:
            print(f"Must be >= {minv}")
            continue
        if maxv is not None and iv > maxv:
            print(f"Must be <= {maxv}")
            continue
        return iv


def prompt_menu(label, options, default_index=1, allow_custom=False):
    while True:
        print(f"\n{label}:")
        for i, opt in enumerate(options, start=1):
            d = " (default)" if i == default_index else ""
            print(f"  {i}. {opt}{d}")

        hi = len(options)
        if allow_custom:
            hi += 1
            print(f"  {hi}. Other")

        choice = input(f"Select 1-{hi} [default: {default_index}]: ").strip()
        if not choice:
            choice = str(default_index)

        if not choice.isdigit():
            print("Enter a number.")
            continue

        n = int(choice)
        if 1 <= n <= len(options):
            return options[n - 1]

        if allow_custom and n == hi:
            custom = input("Enter value: ").strip()
            if custom:
                return custom
            print("Value required.")
            continue

        print("Invalid selection.")


def get_distinct(column):
    if column not in {"Project", "Who"}:
        raise ValueError("Unsupported column.")
    con = db_connect()
    cur = con.cursor()
    rows = cur.execute(
        f"SELECT DISTINCT {column} FROM ActionList "
        f"WHERE {column} IS NOT NULL AND TRIM({column}) <> '' "
        f"ORDER BY {column} COLLATE NOCASE"
    ).fetchall()
    con.close()
    return [r[0] for r in rows if isinstance(r[0], str) and r[0].strip()]


def run_ollama(prompt_text):
    result = subprocess.run(
        ["ollama", "run", MODEL],
        input=prompt_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr)
    return result.stdout.strip()


def extract_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s = text.rfind("{")
        e = text.rfind("}")
        if s >= 0 and e > s:
            return json.loads(text[s:e + 1])
        raise SystemExit("Invalid JSON from model.")


def validate_summary(data):
    """Return error string if schema invalid, else None."""
    if not isinstance(data, dict):
        return "Response is not a JSON object."
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        return "Missing or empty 'title' field."
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        return "Missing or empty 'summary' field."
    bullets = data.get("bullets")
    if not isinstance(bullets, list) or len(bullets) == 0:
        return "'bullets' must be a non-empty list."
    if not all(isinstance(b, str) for b in bullets):
        return "'bullets' must contain only strings."
    return None


def summarize_clipboard(text):
    base_prompt = (
        "Return ONLY JSON. No analysis. No markdown.\n"
        "Summarize into JSON: "
        "{\"title\": string, \"summary\": string, \"bullets\": [string]}.\n"
        "Constraints:\n"
        "- title <= 80 chars\n"
        "- summary <= 3 sentences\n"
        "- bullets: 3-7 items, each <= 120 chars\n"
        "Text:\n" + text
    )

    prompt_text = base_prompt
    max_attempts = 3

    for attempt in range(1, max_attempts + 1):
        output = run_ollama(prompt_text)
        try:
            data = extract_json(output)
        except SystemExit:
            error = "Could not parse JSON from model response."
            data = None
        else:
            error = validate_summary(data)

        if error is None:
            break

        if attempt < max_attempts:
            print(f"Model output invalid (attempt {attempt}): {error} Retrying...")
            prompt_text = (
                base_prompt
                + f"\n\nYour previous response was invalid: {error}"
                + "\nReturn ONLY valid JSON matching the required schema."
            )
        else:
            raise SystemExit(f"Model failed to return valid output after {max_attempts} attempts: {error}")

    title = data["title"].strip()
    summary = data["summary"].strip()
    bullets = data["bullets"]
    bullets_txt = "\n".join(f"- {b}" for b in bullets if isinstance(b, str))
    notes = f"{summary}\n\n{bullets_txt}".strip()

    return title, notes


def insert_task(project, who, status, priority, title, notes):
    con = db_connect()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO ActionList (Project, Who, Status, Priority, Action, Notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project, who[:5], status, priority, title, notes),
    )
    con.commit()
    item_id = cur.lastrowid
    con.close()
    return item_id


def count_open_tasks():
    con = db_connect()
    cur = con.cursor()
    n = cur.execute("SELECT COUNT(*) FROM ActionList WHERE Status <> 'Done'").fetchone()[0]
    con.close()
    return int(n)


def fetch_item(item_id: int):
    con = db_connect()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    row = cur.execute(
        "SELECT ItemID, Project, Who, Status, Priority, Action, Notes "
        "FROM ActionList WHERE ItemID = ?",
        (item_id,),
    ).fetchone()
    con.close()
    return row


def print_item_full(row):
    print("\n=== ITEM DETAIL ===")
    print(f"ItemID  : {row['ItemID']}")
    print(f"Project : {row['Project']}")
    print(f"Who     : {row['Who']}")
    print(f"Status  : {row['Status']}")
    print(f"Priority: {row['Priority']}")
    print(f"Title   : {row['Action']}")
    print("Notes   :")
    print(row["Notes"] or "")
    print("===================\n")


def run_search_query(q: str):
    like = f"%{q}%"
    con = db_connect()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute(
        """
        SELECT ItemID, Project, Who, Status, Priority, Action
        FROM ActionList
        WHERE COALESCE(Project,'') LIKE ?
           OR COALESCE(Action,'')  LIKE ?
           OR COALESCE(Notes,'')   LIKE ?
           OR COALESCE(Who,'')     LIKE ?
        ORDER BY
            CASE Status WHEN 'Open' THEN 1 WHEN 'IP' THEN 2 WHEN 'Wait' THEN 3 WHEN 'Done' THEN 4 ELSE 5 END,
            Priority ASC,
            ItemID DESC
        LIMIT 50
        """,
        (like, like, like, like),
    ).fetchall()
    con.close()
    return rows


def do_search(initial_q=None):
    if initial_q:
        q = initial_q
    else:
        q = prompt("Search text (matches Project/Title/Notes/Who)", required=True)

    while True:
        rows = run_search_query(q)

        print("\n=== SEARCH RESULTS (up to 50) ===")
        if not rows:
            print("(no matches)")
        else:
            for r in rows:
                title = (r["Action"] or "").strip()
                project = (r["Project"] or "").strip()
                print(
                    f'[{r["ItemID"]}] P{r["Priority"]} {r["Status"]:<4} '
                    f'{project} — {title}'
                )

        print("\nOptions:")
        print("  - Enter an ItemID to view full detail")
        print("  - Enter R to refresh results")
        print("  - Enter B to go back to main menu")

        sel = input("Select: ").strip()

        if not sel:
            continue

        if sel.lower() == "b":
            return

        if sel.lower() == "r":
            continue

        if sel.isdigit():
            item_id = int(sel)
            # ensure it matches current search results
            ids = {int(r["ItemID"]) for r in rows}
            if item_id not in ids:
                print("That ItemID is not in the current search results.")
                continue

            row = fetch_item(item_id)
            if not row:
                print("Item no longer exists.")
                continue

            print_item_full(row)

            # after viewing, ask to view another or go back
            nxt = prompt_menu("Next", ["View another from these results", "Back to main menu"], default_index=1)
            if nxt == "Back to main menu":
                return
            # else loop continues (same search term, same results refresh next loop)
            continue

        print("Invalid selection.")


def do_add():
    default_project = "Project X"
    default_who = "RM"
    default_priority = 3
    default_status = "Open"

    projects = get_distinct("Project")
    if default_project not in projects:
        projects.insert(0, default_project)
    project = prompt_menu("Project", projects, default_index=1, allow_custom=True)

    whos = get_distinct("Who")
    if default_who not in whos:
        whos.insert(0, default_who)
    who = prompt_menu("Who (max 5 chars)", whos, default_index=1, allow_custom=True)[:5]

    status_index = ALLOWED_STATUS.index(default_status) + 1
    status = prompt_menu("Status", ALLOWED_STATUS, default_index=status_index)

    priority = prompt_int("Priority (1-5)", default=default_priority, minv=1, maxv=5)

    title = ""
    notes = ""

    if HAS_CLIP:
        use_clip = prompt_menu("Use clipboard summary for Title/Notes?", ["Yes", "No"], default_index=1)
        if use_clip == "Yes":
            clip_text = (pyperclip.paste() or "").strip()
            if clip_text:
                print("\nSummarizing clipboard with Ollama...\n")
                title, notes = summarize_clipboard(clip_text)
                print("Proposed Title:")
                print(title)
                print("\nProposed Notes:")
                print(notes)
                accept = prompt_menu("Accept?", ["Yes", "No"], default_index=1)
                if accept != "Yes":
                    title = prompt("Title", required=True)
                    notes = prompt("Notes", default="")
            else:
                print("Clipboard empty.")
                title = prompt("Title", required=True)
                notes = prompt("Notes", default="")
        else:
            title = prompt("Title", required=True)
            notes = prompt("Notes", default="")
    else:
        title = prompt("Title", required=True)
        notes = prompt("Notes", default="")

    print("\n=== PREVIEW ===")
    print("Project :", project)
    print("Who     :", who)
    print("Status  :", status)
    print("Priority:", priority)
    print("Title   :", title)
    print("Notes   :", notes)

    confirm = prompt_menu("Write to SQLite?", ["Yes", "No"], default_index=1)
    if confirm != "Yes":
        print("Cancelled.")
        input("\nPress Enter to return...")
        return

    item_id = insert_task(project, who, status, priority, title, notes)
    print(f"OK: added ItemID={item_id}")
    input("\nPress Enter to return...")


def main():
    ensure_project_column()

    while True:
        open_count = count_open_tasks()
        set_cmd_ui(f"Task List — Open/IP/Wait: {open_count}")

        print("\nTask List")
        print("---------")
        print("  1. Search   (or: 1 <search term>)")
        print("  2. Add New")
        print("  3. Quit")
        raw = input("Choose: ").strip()

        if not raw or raw == "3":
            print("Bye.")
            break
        elif raw == "2":
            do_add()
        elif raw == "1":
            do_search()
        elif raw.startswith("1 "):
            do_search(initial_q=raw[2:].strip())
        else:
            print("Invalid selection.")


if __name__ == "__main__":
    main()