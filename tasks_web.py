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


def fetch_all(project=None, who=None, statuses=None, sort="ItemID", direction="desc"):
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
    if statuses:
        placeholders = ",".join("?" * len(statuses))
        wheres.append(f"Status IN ({placeholders})")
        params.extend(statuses)

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

    /* Column resize */
    .resizable-table th { position: relative; overflow: hidden; }
    .resize-handle {
      position: absolute; right: 0; top: 0;
      width: 6px; height: 100%;
      cursor: col-resize; user-select: none;
      background: rgba(255,255,255,0.15);
    }
    .resize-handle:hover, .resize-handle.dragging { background: rgba(255,255,255,0.45); }

    /* Print */
    @media print {
      @page { size: landscape; margin: 1cm; }
      .no-print { display: none !important; }
      nav { display: none !important; }
      body { padding-top: 0 !important; }
      .badge-Open     { background-color: #0d6efd !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-IP       { background-color: #fd7e14 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-Wait     { background-color: #6c757d !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-Done     { background-color: #198754 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-Deferred { background-color: #adb5bd !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .table-dark th  { background-color: #212529 !important; color: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      table { width: 100% !important; font-size: 10pt; }
      .print-header { display: block !important; }
    }
    .print-header { display: none; margin-bottom: 8px; font-size: 11pt; }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark fixed-top no-print">
  <div class="container-fluid">
    <a class="navbar-brand" href="/">Task List</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav me-auto">
        <li class="nav-item"><a class="nav-link" href="/">Tasks</a></li>
        <li class="nav-item"><a class="nav-link" href="/add">Add Task</a></li>
      </ul>
    </div>
  </div>
</nav>
<div class="container-fluid mt-3">
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

<!-- Print header (hidden on screen) -->
<div class="print-header">
  <strong>Task List</strong>
  {% if sel_project %} &mdash; Project: {{ sel_project }}{% endif %}
  {% if sel_who %} &mdash; User: {{ sel_who }}{% endif %}
  {% if sel_statuses %} &mdash; Status: {{ sel_statuses | join(', ') }}{% endif %}
  &nbsp;({{ rows|length }} tasks)
</div>

<!-- Toolbar -->
<div class="d-flex justify-content-between align-items-center mb-3 no-print">
  <h4 class="mb-0">Tasks <span class="badge bg-secondary">{{ rows|length }}</span></h4>
  <div class="d-flex gap-2">
    <button onclick="window.print()" class="btn btn-outline-secondary btn-sm">Print</button>
    <a href="/add" class="btn btn-primary btn-sm">+ Add Task</a>
  </div>
</div>

<!-- Filters -->
<form method="get" class="row g-2 mb-3 align-items-end no-print">
  <div class="col-auto">
    <label class="form-label mb-1 small">Project</label>
    <select name="project" class="form-select form-select-sm">
      <option value="">All Projects</option>
      {% for p in projects %}
        <option value="{{ p }}" {% if p == sel_project %}selected{% endif %}>{{ p }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto">
    <label class="form-label mb-1 small">User</label>
    <select name="who" class="form-select form-select-sm">
      <option value="">All Users</option>
      {% for w in whos %}
        <option value="{{ w }}" {% if w == sel_who %}selected{% endif %}>{{ w }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto">
    <label class="form-label mb-1 small">Status</label>
    <div class="d-flex flex-wrap gap-2 pt-1">
      {% for s in all_statuses %}
        <div class="form-check form-check-inline mb-0">
          <input class="form-check-input" type="checkbox" name="status" value="{{ s }}"
                 id="st_{{ s }}" {% if s in sel_statuses %}checked{% endif %}>
          <label class="form-check-label small" for="st_{{ s }}">{{ s }}</label>
        </div>
      {% endfor %}
    </div>
  </div>
  <div class="col-auto">
    <button type="submit" class="btn btn-secondary btn-sm">Filter</button>
    <a href="/" class="btn btn-outline-secondary btn-sm">Clear</a>
  </div>
</form>

<!-- Table -->
<div class="table-responsive">
<table class="table table-bordered table-hover table-sm align-middle resizable-table" id="task-table">
  <thead class="table-dark">
    <tr>
      {% for col, label in columns %}
        <th style="min-width:40px;">
          <span class="no-print">
            {% if sort == col and direction == 'asc' %}
              <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=desc{% for s in sel_statuses %}&status={{ s }}{% endfor %}">{{ label }} ▲</a>
            {% elif sort == col %}
              <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=asc{% for s in sel_statuses %}&status={{ s }}{% endfor %}">{{ label }} ▼</a>
            {% else %}
              <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=asc{% for s in sel_statuses %}&status={{ s }}{% endfor %}">{{ label }}</a>
            {% endif %}
          </span>
          <span class="print-only" style="display:none;">{{ label }}</span>
          <div class="resize-handle no-print"></div>
        </th>
      {% endfor %}
      <th style="min-width:80px;">Notes<div class="resize-handle no-print"></div></th>
      <th class="no-print">Actions</th>
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
      <td class="no-print">
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

<style>
  @media print { .print-only { display: inline !important; } }
</style>

<script>
(function() {
  // Column resize
  const table = document.getElementById('task-table');
  if (!table) return;
  table.querySelectorAll('.resize-handle').forEach(handle => {
    let startX, startW, th;
    handle.addEventListener('mousedown', e => {
      th = handle.parentElement;
      startX = e.pageX;
      startW = th.offsetWidth;
      handle.classList.add('dragging');
      const onMove = e => { th.style.width = Math.max(40, startW + (e.pageX - startX)) + 'px'; };
      const onUp = () => {
        handle.classList.remove('dragging');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      e.preventDefault();
    });
  });
})();
</script>
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
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def task_list():
    sel_project = request.args.get("project", "")
    sel_who = request.args.get("who", "")
    sel_statuses = request.args.getlist("status") or list(ALLOWED_STATUS)
    sort = request.args.get("sort", "ItemID")
    direction = request.args.get("dir", "desc")

    rows = fetch_all(
        project=sel_project or None,
        who=sel_who or None,
        statuses=sel_statuses,
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
        all_statuses=ALLOWED_STATUS,
        sel_project=sel_project,
        sel_who=sel_who,
        sel_statuses=sel_statuses,
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
        if project and action:
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


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
