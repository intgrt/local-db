"""
Migration: remove CHECK constraint from ActionList.Status
Run once from the project directory.
"""
import sqlite3
from pathlib import Path

DB = r"D:\Datafiles5\softwarebuilds_other\Local_Task__List\tasks.db"

con = sqlite3.connect(DB)
cur = con.cursor()

# Get current columns
cols = [r[1] for r in cur.execute("PRAGMA table_info(ActionList)").fetchall()]
print("Columns:", cols)

cur.executescript("""
    PRAGMA foreign_keys = OFF;

    ALTER TABLE ActionList RENAME TO ActionList_old;

    CREATE TABLE ActionList (
        ItemID   INTEGER PRIMARY KEY AUTOINCREMENT,
        Project  TEXT,
        Who      TEXT,
        Status   TEXT,
        Priority INTEGER,
        Action   TEXT,
        Notes    TEXT
    );

    INSERT INTO ActionList SELECT ItemID, Project, Who, Status, Priority, Action, Notes
    FROM ActionList_old;

    DROP TABLE ActionList_old;

    PRAGMA foreign_keys = ON;
""")

con.commit()
con.close()
print("Migration complete.")
