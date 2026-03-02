import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import Flask, render_template_string, request, redirect, abort
from urllib.parse import urlencode, quote, unquote
from tasks_db import (
    ALLOWED_STATUS, db_connect, get_distinct, fetch_one,
    insert_task, run_search_query,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# DB helpers (web-only — shared helpers imported from tasks_db)
# ---------------------------------------------------------------------------

def fetch_all(project=None, who=None, statuses=None, sort="ItemID", direction="desc"):
    from tasks_db import STATUS_ORDER
    import sqlite3
    allowed_cols = {"ItemID", "Project", "Who", "Status", "Priority", "Action"}
    if sort not in allowed_cols:
        sort = "ItemID"
    if direction not in ("asc", "desc"):
        direction = "desc"

    con = db_connect()
    con.row_factory = sqlite3.Row
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
        order_clause = f"ORDER BY {STATUS_ORDER} {direction.upper()}, Priority ASC"
    else:
        order_clause = f"ORDER BY {sort} {direction.upper()}"

    rows = cur.execute(
        f"SELECT ItemID, Project, Who, Status, Priority, Action, Notes "
        f"FROM ActionList {where_clause} {order_clause}",
        params,
    ).fetchall()
    con.close()
    return rows


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
    .badge-Open  { background-color: #0d6efd; }
    .badge-IP    { background-color: #fd7e14; }
    .badge-Wait  { background-color: #6c757d; }
    .badge-Done  { background-color: #198754; }
    .badge-Defrd { background-color: #adb5bd; color: #000; }
    .badge-Cncld { background-color: #6f42c1; }
    .notes-cell { max-width: 300px; padding: 0 !important; }
    .notes-cell div { white-space: pre-wrap; font-size: 0.85em; max-height: 2.8em; overflow: hidden; padding: 2px 4px; }
    /* Remove chevron arrow from inline table dropdowns */
    td .form-select { background-image: none; padding-right: 0.5rem; }

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
      .badge-Open  { background-color: #0d6efd !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-IP    { background-color: #fd7e14 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-Wait  { background-color: #6c757d !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-Done  { background-color: #198754 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-Defrd { background-color: #adb5bd !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .badge-Cncld { background-color: #6f42c1 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
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
    <a href="/add?return_to={{ return_to }}" class="btn btn-primary btn-sm">+ Add Task</a>
  </div>
</div>

<!-- Filters -->
<form method="get" class="row g-2 mb-3 align-items-end no-print">
  <div class="col-auto">
    <label class="form-label mb-1 small">Search</label>
    <input type="text" name="q" class="form-control form-control-sm" placeholder="Project / Title / Notes / Who"
           value="{{ q }}" style="min-width:220px;">
  </div>
  <div class="col-auto">
    <label class="form-label mb-1 small">Project</label>
    <select name="project" class="form-select form-select-sm" {% if q %}disabled{% endif %}>
      <option value="">All Projects</option>
      {% for p in projects %}
        <option value="{{ p }}" {% if p == sel_project %}selected{% endif %}>{{ p }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto">
    <label class="form-label mb-1 small">User</label>
    <select name="who" class="form-select form-select-sm" {% if q %}disabled{% endif %}>
      <option value="">All Users</option>
      {% for w in whos %}
        <option value="{{ w }}" {% if w == sel_who %}selected{% endif %}>{{ w }}</option>
      {% endfor %}
    </select>
  </div>
  <div class="col-auto" {% if q %}style="opacity:0.4;pointer-events:none;"{% endif %}>
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
    <button type="submit" class="btn btn-secondary btn-sm">Go</button>
    <a href="/" class="btn btn-outline-secondary btn-sm">Clear</a>
  </div>
</form>
{% if q %}
<div class="alert alert-info py-1 px-2 mb-2 no-print small">
  Searching: <strong>{{ q }}</strong> &mdash; {{ rows|length }} result(s)
</div>
{% endif %}

<!-- Table -->
<div class="table-responsive">
<table class="table table-bordered table-hover table-sm align-middle resizable-table" id="task-table">
  <colgroup>
    <col style="width:3%"><!-- ID -->
    <col style="width:5%"><!-- Project -->
    <col style="width:4%"><!-- Who -->
    <col style="width:4%"><!-- Status -->
    <col style="width:4%"><!-- Pri -->
    <col style="width:22%"><!-- Title -->
    <col style="width:30%"><!-- Notes -->
    <col style="width:8%"><!-- Actions -->
  </colgroup>
  <thead class="table-dark">
    <tr>
      {% for col, label in columns %}
        {% if col in ('Who', 'Status', 'Priority') %}
          <th class="no-print" style="min-width:40px;">
            {% if sort == col and direction == 'asc' %}
              <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=desc{% for s in sel_statuses %}&status={{ s }}{% endfor %}">{{ label }} ▲</a>
            {% elif sort == col %}
              <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=asc{% for s in sel_statuses %}&status={{ s }}{% endfor %}">{{ label }} ▼</a>
            {% else %}
              <a href="?project={{ sel_project }}&who={{ sel_who }}&sort={{ col }}&dir=asc{% for s in sel_statuses %}&status={{ s }}{% endfor %}">{{ label }}</a>
            {% endif %}
            <div class="resize-handle"></div>
          </th>
          <th class="print-who print-status print-priority" style="display:none;">{{ label }}</th>
        {% else %}
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
        {% endif %}
      {% endfor %}
      <th style="min-width:80px;">Notes<div class="resize-handle no-print"></div></th>
      <th class="no-print">Actions</th>
    </tr>
  </thead>
  <tbody>
    {% for r in rows %}
    <tr id="row-{{ r['ItemID'] }}">
      <td>{{ r['ItemID'] }}</td>
      <td>{{ r['Project'] or '' }}</td>
      <td class="no-print">
        <form method="post" action="/quick-update/{{ r['ItemID'] }}">
          <input type="hidden" name="return_to" value="{{ return_to }}">
          <input type="hidden" name="anchor" value="row-{{ r['ItemID'] }}">
          <select name="who" class="form-select form-select-sm" onchange="this.form.submit()" style="min-width:70px;">
            {% for w in whos %}
              <option value="{{ w }}" {% if w == r['Who'] %}selected{% endif %}>{{ w }}</option>
            {% endfor %}
            {% if r['Who'] not in whos %}
              <option value="{{ r['Who'] }}" selected>{{ r['Who'] }}</option>
            {% endif %}
          </select>
        </form>
      </td>
      <td class="print-who" style="display:none;">{{ r['Who'] or '' }}</td>
      <td class="no-print">
        <form method="post" action="/quick-update/{{ r['ItemID'] }}">
          <input type="hidden" name="return_to" value="{{ return_to }}">
          <input type="hidden" name="anchor" value="row-{{ r['ItemID'] }}">
          <select name="status" class="form-select form-select-sm" onchange="this.form.submit()">
            {% for s in all_statuses %}
              <option value="{{ s }}" {% if s == r['Status'] %}selected{% endif %}>{{ s }}</option>
            {% endfor %}
          </select>
        </form>
      </td>
      <td class="print-status" style="display:none;"><span class="badge badge-{{ r['Status'] }}">{{ r['Status'] }}</span></td>
      <td class="no-print">
        <form method="post" action="/quick-update/{{ r['ItemID'] }}">
          <input type="hidden" name="return_to" value="{{ return_to }}">
          <input type="hidden" name="anchor" value="row-{{ r['ItemID'] }}">
          <select name="priority" class="form-select form-select-sm" onchange="this.form.submit()" style="min-width:60px;">
            {% for p in [1,2,3,4,5] %}
              <option value="{{ p }}" {% if p == r['Priority'] %}selected{% endif %}>{{ p }}</option>
            {% endfor %}
          </select>
        </form>
      </td>
      <td class="print-priority" style="display:none;">{{ r['Priority'] }}</td>
      <td>{{ r['Action'] or '' }}</td>
      <td class="notes-cell"><div>{{ r['Notes'] or '' }}</div></td>
      <td class="no-print">
        <a href="/edit/{{ r['ItemID'] }}?return_to={{ return_to }}" class="btn btn-outline-primary btn-sm">Edit</a>
        <form method="post" action="/delete/{{ r['ItemID'] }}" class="d-inline"
              onsubmit="return confirm('Delete item {{ r['ItemID'] }}?')">
          <input type="hidden" name="return_to" value="{{ return_to }}">
          <button type="submit" class="btn btn-outline-danger btn-sm">Del</button>
        </form>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
</div>

<style>
  @media print {
    .print-only { display: inline !important; }
    .print-who, .print-status, .print-priority { display: table-cell !important; }
  }
</style>

<script>
(function() {
  // Scroll to anchor after quick-update redirect
  if (window.location.hash) {
    const el = document.querySelector(window.location.hash);
    if (el) el.scrollIntoView({ block: 'center' });
  }

  // Status dropdown colours
  const STATUS_COLORS = {
    'Open':  { bg: '#0d6efd', color: '#fff' },
    'IP':    { bg: '#fd7e14', color: '#fff' },
    'Wait':  { bg: '#6c757d', color: '#fff' },
    'Done':  { bg: '#198754', color: '#fff' },
    'Defrd': { bg: '#adb5bd', color: '#000' },
    'Cncld': { bg: '#6f42c1', color: '#fff' },
  };
  function applyStatusColor(sel) {
    const c = STATUS_COLORS[sel.value];
    if (c) { sel.style.backgroundColor = c.bg; sel.style.color = c.color; }
    else   { sel.style.backgroundColor = ''; sel.style.color = ''; }
  }
  document.querySelectorAll('select[name="status"]').forEach(sel => {
    applyStatusColor(sel);
    sel.addEventListener('change', () => applyStatusColor(sel));
  });

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
    <h4 class="mb-2">{{ form_title }}</h4>
    <form method="post">
      <div class="mb-1">
        <label class="form-label mb-0">Project</label>
        <select name="project" id="project-select" class="form-select" onchange="toggleOther(this,'project-other')">
          <option value="">-- Select --</option>
          {% for p in projects %}
            <option value="{{ p }}" {% if p == (task.Project or '') %}selected{% endif %}>{{ p }}</option>
          {% endfor %}
          <option value="__other__" {% if task.Project and task.Project not in projects %}selected{% endif %}>Other...</option>
        </select>
        <input type="text" id="project-other" name="project_other" class="form-control mt-1"
               placeholder="Enter new project name"
               value="{{ task.Project if task.Project and task.Project not in projects else '' }}"
               style="display:{% if task.Project and task.Project not in projects %}block{% else %}none{% endif %};">
      </div>
      <div class="mb-1">
        <label class="form-label mb-0">Who <small class="text-muted">(max 5 chars)</small></label>
        <select name="who" id="who-select" class="form-select" onchange="toggleOther(this,'who-other')">
          <option value="">-- Select --</option>
          {% for w in whos %}
            <option value="{{ w }}" {% if w == (task.Who or '') %}selected{% endif %}>{{ w }}</option>
          {% endfor %}
          <option value="__other__" {% if task.Who and task.Who not in whos %}selected{% endif %}>Other...</option>
        </select>
        <input type="text" id="who-other" name="who_other" class="form-control mt-1"
               placeholder="Enter new name (max 5 chars)" maxlength="5"
               value="{{ task.Who if task.Who and task.Who not in whos else '' }}"
               style="display:{% if task.Who and task.Who not in whos %}block{% else %}none{% endif %};">
      </div>
      <div class="mb-1">
        <label class="form-label mb-0">Status</label>
        <select name="status" class="form-select">
          {% for s in statuses %}
            <option value="{{ s }}" {% if s == (task.Status or 'Open') %}selected{% endif %}>{{ s }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="mb-1">
        <label class="form-label mb-0">Priority <small class="text-muted">(1 low – 5 high)</small></label>
        <input type="number" name="priority" class="form-control" min="1" max="5"
               value="{{ task.Priority or 3 }}" required>
      </div>
      <div class="mb-1">
        <label class="form-label mb-0">Title / Action</label>
        <input type="text" name="action" class="form-control" value="{{ task.Action or '' }}" required>
      </div>
      <div class="mb-1">
        <label class="form-label mb-0">Notes</label>
        <textarea name="notes" class="form-control" rows="10">{{ task.Notes or '' }}</textarea>
      </div>
      <input type="hidden" name="return_to" value="{{ return_to }}">
      <div class="mt-2">
      <button type="submit" class="btn btn-primary">Save</button>
      <a href="{{ return_to or '/' }}" class="btn btn-secondary ms-2">Cancel</a>
      </div>
    </form>
  </div>
</div>
<script>
function toggleOther(sel, otherId) {
  const other = document.getElementById(otherId);
  if (sel.value === '__other__') {
    other.style.display = 'block';
    other.focus();
  } else {
    other.style.display = 'none';
  }
}
// Before submit: copy "other" text inputs into the select value so POST picks them up
document.querySelector('form').addEventListener('submit', function() {
  ['project', 'who'].forEach(function(field) {
    const sel = document.getElementById(field + '-select');
    const other = document.getElementById(field + '-other');
    if (sel && sel.value === '__other__' && other && other.value.trim()) {
      sel.value = other.value.trim();
      sel.name = field;
      other.disabled = true;
    }
  });
});
</script>
{% endblock %}
""")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def task_list():
    q = request.args.get("q", "").strip()
    sel_project = request.args.get("project", "")
    sel_who = request.args.get("who", "")
    sel_statuses = request.args.getlist("status") or ["Open", "IP", "Wait"]
    sort = request.args.get("sort", "Priority")
    direction = request.args.get("dir", "desc")

    # Build return_to so edit/delete can restore this exact view
    qs_parts = []
    if q:
        qs_parts.append(("q", q))
    if sel_project:
        qs_parts.append(("project", sel_project))
    if sel_who:
        qs_parts.append(("who", sel_who))
    for s in sel_statuses:
        qs_parts.append(("status", s))
    if sort != "Priority":
        qs_parts.append(("sort", sort))
    if direction != "desc":
        qs_parts.append(("dir", direction))
    return_to = quote("/?" + urlencode(qs_parts), safe="") if qs_parts else "%2F"

    if q:
        rows = run_search_query(q)
    else:
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
        q=q,
        sel_project=sel_project,
        sel_who=sel_who,
        sel_statuses=sel_statuses,
        sort=sort,
        direction=direction,
        columns=columns,
        return_to=return_to,
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
        return_to = unquote(request.form.get("return_to", "%2F"))
        if project and action:
            insert_task(project, who, status, priority, action, notes)
            return redirect(return_to)

    return_to = request.args.get("return_to", "%2F")
    class Empty:
        Project = Who = Status = Action = Notes = ""
        Priority = 3

    return render_template_string(
        TASK_FORM,
        form_title="Add Task",
        task=Empty(),
        statuses=ALLOWED_STATUS,
        projects=get_distinct("Project"),
        whos=get_distinct("Who"),
        return_to=return_to,
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
        return_to = unquote(request.form.get("return_to", "%2F"))
        update_task(item_id, project, who, status, priority, action, notes)
        return redirect(return_to)

    return_to = request.args.get("return_to", "%2F")
    return render_template_string(
        TASK_FORM,
        form_title=f"Edit Task #{item_id}",
        task=row,
        statuses=ALLOWED_STATUS,
        projects=get_distinct("Project"),
        whos=get_distinct("Who"),
        return_to=return_to,
    )


@app.route("/quick-update/<int:item_id>", methods=["POST"])
def quick_update(item_id):
    row = fetch_one(item_id)
    if row is None:
        abort(404)
    # Apply only the field(s) submitted; keep existing values for the rest
    who = request.form.get("who", row["Who"] or "").strip()
    status = request.form.get("status", row["Status"] or "Open")
    priority = request.form.get("priority", row["Priority"] or 3)
    update_task(item_id, row["Project"] or "", who, status, priority,
                row["Action"] or "", row["Notes"] or "")
    anchor = request.form.get("anchor", f"row-{item_id}")
    return_to = unquote(request.form.get("return_to", "%2F"))
    return redirect(return_to + f"#{anchor}")


@app.route("/delete/<int:item_id>", methods=["POST"])
def delete_task_route(item_id):
    row = fetch_one(item_id)
    if row is None:
        abort(404)
    return_to = unquote(request.form.get("return_to", "%2F"))
    delete_task(item_id)
    return redirect(return_to)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
