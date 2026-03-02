import sqlite3
from pathlib import Path

DB = r"D:\Datafiles5\softwarebuilds_other\Local_Task__List\tasks.db"

ALLOWED_STATUS = ["Open", "IP", "Wait", "Done", "Defrd", "Cncld"]

STATUS_ORDER = (
    "CASE Status "
    "WHEN 'Open'  THEN 1 "
    "WHEN 'IP'    THEN 2 "
    "WHEN 'Wait'  THEN 3 "
    "WHEN 'Done'  THEN 4 "
    "WHEN 'Defrd' THEN 5 "
    "WHEN 'Cncld' THEN 6 "
    "ELSE 7 END"
)


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


def fetch_one(item_id: int):
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


def insert_task(project, who, status, priority, title, notes):
    con = db_connect()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO ActionList (Project, Who, Status, Priority, Action, Notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project, who[:5], status, int(priority), title, notes),
    )
    con.commit()
    item_id = cur.lastrowid
    con.close()
    return item_id


def count_open_tasks():
    con = db_connect()
    cur = con.cursor()
    n = cur.execute(
        "SELECT COUNT(*) FROM ActionList WHERE Status NOT IN ('Done', 'Cncld')"
    ).fetchone()[0]
    con.close()
    return int(n)


def run_search_query(q: str):
    like = f"%{q}%"
    con = db_connect()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute(
        f"""
        SELECT ItemID, Project, Who, Status, Priority, Action, Notes
        FROM ActionList
        WHERE COALESCE(Project,'') LIKE ?
           OR COALESCE(Action,'')  LIKE ?
           OR COALESCE(Notes,'')   LIKE ?
           OR COALESCE(Who,'')     LIKE ?
        ORDER BY {STATUS_ORDER}, Priority ASC, ItemID DESC
        """,
        (like, like, like, like),
    ).fetchall()
    con.close()
    return rows
