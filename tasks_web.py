import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template_string, request, redirect, url_for, abort
from tasks_cli_interactive import db_connect, ALLOWED_STATUS

app = Flask(__name__)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

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
    return [r[0] for r in rows]


def fetch_all(project=None, who=None, sort="ItemID", direction="desc"):
    allowed_cols = {"ItemID", "Project", "Who", "Status", "Priority", "Action"}
    if sort not in allowed_cols:
        sort = "ItemID"
    if direction not in ("asc", "desc"):
        direction = "desc"

    status_order = "CASE Status WHEN 'Open' THEN 1 WHEN 'IP' THEN 2 WHEN 'Wait' THEN 3 WHEN 'Done' THEN 4 ELSE 5 END"

    con = db_connect()
    con.row_factory = __import__("sqlite3").Row
    cur = con.cursor()

    wheres = []
    params = []
    if project:
        wheres.append("Project = ?")
        params.append(project)
    if who:
        wheres.append("Who = ?")
        params.append(who)

    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    if sort == "Status":
        order_clause = f"ORDER BY {status_order} {direction.upper()}, Priority ASC"
    else:
        order_clause = f"ORDER BY {sort} {direction.upper()}"

    rows = cur.execute(
        f"SELECT ItemID, Project, Who, Status, Priority, Action, Notes "
        f"FROM ActionList {where_clause} {order_clause}",
        params,
    ).fetchall()
    con.close()
    return rows


def fetch_one(item_id):
    con = db_connect()
    con.row_factory = __import__("sqlite3").Row
    cur = con.cursor()
    row = cur.execute(
        "SELECT ItemID, Project, Who, Status, Priority, Action, Notes "
        "FROM ActionList WHERE ItemID = ?", (item_id,)
    ).fetchone()
    con.close()
    return row


def insert_task(project, who, status, priority, action, notes):
    con = db_connect()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO ActionList (Project, Who, Status, Priority, Action, Notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (project, who[:5], status, int(priority), action, notes),
    )
    con.commit()
    item_id = cur.lastrowid
    con.close()
    return item_id


def update_task(item_id, project, who, status, priority, action, notes):
    con = db_connect()
    cur = con.cursor()
    cur.execute(
        "UPDATE ActionList SET Project=?, Who=?, Status=?, Priority=?, Action=?, Notes=? "
        "WHERE ItemID=?",
        (project, who[:5], status, int(priority), action, notes, item_id),
    )
    con.commit()
    con.close()


def delete_task(item_id):
    con = db_connect()
    cur = con.cursor()
    cur.execute("DELETE FROM ActionList WHERE ItemID = ?", (item_id,))
    con.commit()
    con.close()


def get_reports(who=None):
    con = db_connect()
    con.row_factory = __import__("sqlite3").Row
    cur = con.cursor()
    wheres = []
    params = []
    if who:
        wheres.append("Who = ?")
        params.append(who)
    where_clause = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    rows = cur.execute(
        f"SELECT COALESCE(Project,'(none)') as Project, Status, COUNT(*) as Cnt "
        f"FROM ActionList {where_clause} "
        f"GROUP BY Project, Status "
        f"ORDER BY Project COLLATE NOCASE, "
        f"CASE Status WHEN 'Open' THEN 1 WHEN 'IP' THEN 2 WHEN 'Wait' THEN 3 WHEN 'Done' THEN 4 ELSE 5 END",
        params,
    ).fetchall()
    con.close()
    # Pivot: {project: {status: count}}
    data = {}
    for r in rows:
        p = r["Project"]
        if p not in data:
            data[p] = {s: 0 for s in ALLOWED_STATUS}
        data[p][r["Status"]] = r["Cnt"]
    # Row totals
    totals = {s: 0 for s in ALLOWED_STATUS}
    for p_data in data.values():
        for s in ALLOWED_STATUS:
            totals[s] += p_data.get(s, 0)
    return data, totals


# ---------------------------------------------------------------------------
# Base template
# ---------------------------------------------------------------------------

BASE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Task List</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { padding-top: 60px; }
    .table th a { color: inherit; text-decoration: none; }
    .table th a:hover { text-decoration: underline; }
    .badge-Open     { background-color: #0d6efd; }
    .badge-IP       { background-color: #fd7e14; }
    .badge-Wait     { background-color: #6c757d; }
    .badge-Done     { background-color: #198754; }
    .badge-Deferred { background-color: #adb5bd; color: #000; }
    .notes-cell { max-width: 300px; white-space: pre-wrap; font-size: 0.85em; }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top">
  <div class="container-fluid">
    <a class="navbar-brand" href="/">Task List</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav me-auto">
        <li class="nav-item"><a class="nav-link" href="/">Tasks</a></li>
        <li class="nav-item"><a class="nav-link" href="/reports">Reports</a></li>
        <li class="nav-item"><a class="nav-link" href="/add">Add Task</a></li>
      </ul>
    </div>
  </div>
</nav>
<div class="container-fluid mt-3">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="alert alert-{{ cat }} alert-dismissible fade show" role="alert">
        {{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Task list template
# ---------------------------------------------------------------------------

TASK_LIST = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">Tasks <span class="badge bg-secondary">{{ rows|length }}</span></h4>
  <a href="/add" class="btn btn-primary btn-sm">+ Add Task</a>
</div>

<form method="get" class="row g-2 mb-3">
  <div class="col-auto">
    <select name="project" class="form-select form-select-sm">
      <option value="">All Projects</option>
      {% for p in projects %}
        <option value="{{ p }}" {% if p == sel_project %}selected{% endif %}>{{ p }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto">
    <select name="who" class="form-select form-select-sm">
      <option value="">All Users</option>
      {% for w in whos %}
        <option value="{{ w }}" {% if w == sel_who %}selected{% endif %}>{{ w }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-secondary btn-sm">Filter</button>
    <a href="/" class="btn btn-outline-secondary btn-sm">Clear</a>
  </div>
</form>

<div class="table-responsive">
<table class="table table-bordered table-hover table-sm align-middle">
  <thead class="table-dark">
    <tr>
      {% for col, label in columns %}
        <th>
          {% if sort == col and direction == 'asc' %}
            <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=desc">{{ label }} ▲</a>
          {% elif sort == col %}
            <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=asc">{{ label }} ▼</a>
          {% else %}
            <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=asc">{{ label }}</a>
          {% endif %}
        </th>
      {% endfor %}
      <th>Notes</th>
      <th>Actions</th>
    </tr>
  </thead>
  <tbody>
    {% for r in rows %}
    <tr>
      <td>{{ r['ItemID'] }}</td>
      <td>{{ r['Project'] or '' }}</td>
      <td>{{ r['Who'] or '' }}</td>
      <td><span class="badge badge-{{ r['Status'] }}">{{ r['Status'] }}</span></td>
      <td>{{ r['Priority'] }}</td>
      <td>{{ r['Action'] or '' }}</td>
      <td class="notes-cell">{{ r['Notes'] or '' }}</td>
      <td>
        <a href="/edit/{{ r['ItemID'] }}" class="btn btn-outline-primary btn-sm">Edit</a>
        <form method="post" action="/delete/{{ r['ItemID'] }}" class="d-inline"
              onsubmit="return confirm('Delete item {{ r['ItemID'] }}?')">
          <button type="submit" class="btn btn-outline-danger btn-sm">Del</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}
""")

# ---------------------------------------------------------------------------
# Add / Edit form template
# ---------------------------------------------------------------------------

TASK_FORM = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="row justify-content-center">
  <div class="col-lg-7">
    <h4 class="mb-3">{{ form_title }}</h4>
    <form method="post">
      <div class="mb-3">
        <label class="form-label">Project</label>
        <input type="text" name="project" class="form-control" value="{{ task.Project or '' }}" required>
      </div>
      <div class="mb-3">
        <label class="form-label">Who <small class="text-muted">(max 5 chars)</small></label>
        <input type="text" name="who" class="form-control" maxlength="5" value="{{ task.Who or '' }}">
      </div>
      <div class="mb-3">
        <label class="form-label">Status</label>
        <select name="status" class="form-select">
          {% for s in statuses %}
            <option value="{{ s }}" {% if s == (task.Status or 'Open') %}selected{% endif %}>{{ s }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="mb-3">
        <label class="form-label">Priority <small class="text-muted">(1 low – 5 high)</small></label>
        <input type="number" name="priority" class="form-control" min="1" max="5"
               value="{{ task.Priority or 3 }}" required>
      </div>
      <div class="mb-3">
        <label class="form-label">Title / Action</label>
        <input type="text" name="action" class="form-control" value="{{ task.Action or '' }}" required>
      </div>
      <div class="mb-3">
        <label class="form-label">Notes</label>
        <textarea name="notes" class="form-control" rows="5">{{ task.Notes or '' }}</textarea>
      </div>
      <button type="submit" class="btn btn-primary">Save</button>
      <a href="/" class="btn btn-secondary ms-2">Cancel</a>
    </form>
  </div>
</div>
{% endblock %}
""")

# ---------------------------------------------------------------------------
# Reports template
# ---------------------------------------------------------------------------

REPORTS = BASE.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">Reports — Tasks by Project &amp; Status</h4>
</div>

<form method="get" class="row g-2 mb-3">
  <div class="col-auto">
    <select name="who" class="form-select form-select-sm">
      <option value="">All Users</option>
      {% for w in whos %}
        <option value="{{ w }}" {% if w == sel_who %}selected{% endif %}>{{ w }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-secondary btn-sm">Filter</button>
    <a href="/reports" class="btn btn-outline-secondary btn-sm">Clear</a>
  </div>
</form>

<div class="table-responsive">
<table class="table table-bordered table-sm align-middle">
  <thead class="table-dark">
    <tr>
      <th>Project</th>
      {% for s in statuses %}
        <th class="text-center">{{ s }}</th>
      {% endfor %}
      <th class="text-center">Total</th>
    </tr>
  </thead>
  <tbody>
    {% for project, counts in data.items() %}
    <tr>
      <td>{{ project }}</td>
      {% for s in statuses %}
        <td class="text-center">
          {% if counts[s] > 0 %}
            <span class="badge badge-{{ s }}">{{ counts[s] }}</span>
          {% else %}
            <span class="text-muted">—</span>
          {% endif %}
        </td>
      {% endfor %}
      <td class="text-center fw-bold">{{ counts.values()|sum }}</td>
    </tr>
    {% endfor %}
  </tbody>
  <tfoot class="table-secondary">
    <tr>
      <td><strong>Total</strong></td>
      {% for s in statuses %}
        <td class="text-center"><strong>{{ totals[s] }}</strong></td>
      {% endfor %}
      <td class="text-center"><strong>{{ totals.values()|sum }}</strong></td>
    </tr>
  </tfoot>
</table>
</div>
{% endblock %}
""")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def task_list():
    sel_project = request.args.get("project", "")
    sel_who = request.args.get("who", "")
    sort = request.args.get("sort", "ItemID")
    direction = request.args.get("dir", "desc")

    rows = fetch_all(
        project=sel_project or None,
        who=sel_who or None,
        sort=sort,
        direction=direction,
    )
    columns = [
        ("ItemID", "ID"),
        ("Project", "Project"),
        ("Who", "Who"),
        ("Status", "Status"),
        ("Priority", "Pri"),
        ("Action", "Title"),
    ]
    return render_template_string(
        TASK_LIST,
        rows=rows,
        projects=get_distinct("Project"),
        whos=get_distinct("Who"),
        sel_project=sel_project,
        sel_who=sel_who,
        sort=sort,
        direction=direction,
        columns=columns,
    )


@app.route("/add", methods=["GET", "POST"])
def add_task():
    if request.method == "POST":
        project = request.form.get("project", "").strip()
        who = request.form.get("who", "").strip()
        status = request.form.get("status", "Open")
        priority = request.form.get("priority", 3)
        action = request.form.get("action", "").strip()
        notes = request.form.get("notes", "").strip()
        if not project or not action:
            pass  # fall through to re-render with values intact
        else:
            insert_task(project, who, status, priority, action, notes)
            return redirect(url_for("task_list"))

    class Empty:
        Project = Who = Status = Action = Notes = ""
        Priority = 3

    return render_template_string(
        TASK_FORM,
        form_title="Add Task",
        task=Empty(),
        statuses=ALLOWED_STATUS,
    )


@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
def edit_task(item_id):
    row = fetch_one(item_id)
    if row is None:
        abort(404)

    if request.method == "POST":
        project = request.form.get("project", "").strip()
        who = request.form.get("who", "").strip()
        status = request.form.get("status", "Open")
        priority = request.form.get("priority", 3)
        action = request.form.get("action", "").strip()
        notes = request.form.get("notes", "").strip()
        update_task(item_id, project, who, status, priority, action, notes)
        return redirect(url_for("task_list"))

    return render_template_string(
        TASK_FORM,
        form_title=f"Edit Task #{item_id}",
        task=row,
        statuses=ALLOWED_STATUS,
    )


@app.route("/delete/<int:item_id>", methods=["POST"])
def delete_task_route(item_id):
    row = fetch_one(item_id)
    if row is None:
        abort(404)
    delete_task(item_id)
    return redirect(url_for("task_list"))


@app.route("/reports")
def reports():
    sel_who = request.args.get("who", "")
    data, totals = get_reports(who=sel_who or None)
    return render_template_string(
        REPORTS,
        data=data,
        totals=totals,
        statuses=ALLOWED_STATUS,
        whos=get_distinct("Who"),
        sel_who=sel_who,
    )


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
