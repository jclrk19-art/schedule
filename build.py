#!/usr/bin/env python3
"""
build.py — regenerates index.html from /data.

Usage:  python3 build.py
Rules:  never hand-edit index.html; edit data/*.json and re-run this.
        Running twice on the same data produces identical output (idempotent).
Stdlib only — no dependencies.
"""

import json
import html
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "index.html"

DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]  # date.weekday() order
WEEK_START_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
PX_PER_HOUR = 48


# ---------- helpers ----------

def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt_time(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d}{suffix}" if m else f"{h12}{suffix}"


def fmt_hour(h):
    suffix = "am" if h < 12 else "pm"
    return f"{h % 12 or 12} {suffix}"


def hours_fmt(x):
    return f"{x:g}"


def esc(s):
    return html.escape(str(s), quote=True)


# ---------- load & expand ----------

def load():
    sched = json.loads((DATA / "schedule.json").read_text())
    rec = json.loads((DATA / "recurring.json").read_text())
    return sched, rec


def expand_recurring(rules, start, end, explicit_events):
    """Expand rules into concrete blocks across [start, end].
    A rule is skipped on a date if: date in skip_dates, outside valid range,
    or an explicit event on that date declares  "replaces": "<rule_id>"."""
    replaced = {(e["date"], e.get("replaces")) for e in explicit_events if e.get("replaces")}
    out = []
    day = start
    while day <= end:
        dow = DOW[day.weekday()]
        iso = day.isoformat()
        for r in rules:
            if dow not in r.get("days", []):
                continue
            if iso in r.get("skip_dates", []):
                continue
            if r.get("valid_from") and day < d(r["valid_from"]):
                continue
            if r.get("valid_until") and day > d(r["valid_until"]):
                continue
            if (iso, r["id"]) in replaced:
                continue
            ov = r.get("day_overrides", {}).get(dow, {})
            out.append({
                "id": f"{iso}-{r['id']}",
                "date": iso,
                "start": ov.get("start", r["start"]),
                "end": ov.get("end", r["end"]),
                "title": r["title"],
                "category": r["category"],
                "recurring": True,
            })
        day += timedelta(days=1)
    return out


# ---------- validation ----------

def validate(events, cfg):
    problems = []
    win_s, win_e = minutes(cfg["day_window"]["start"]), minutes(cfg["day_window"]["end"])
    by_date = {}
    for e in events:
        if minutes(e["end"]) <= minutes(e["start"]):
            problems.append(f"  ! {e['id']}: end <= start")
        if minutes(e["start"]) < win_s or minutes(e["end"]) > win_e:
            problems.append(f"  ~ {e['id']}: outside day window {cfg['day_window']['start']}-{cfg['day_window']['end']} (grid will auto-expand)")
        if e["category"] not in cfg["categories"]:
            problems.append(f"  ! {e['id']}: unknown category '{e['category']}' — add it to config.categories")
        by_date.setdefault(e["date"], []).append(e)
    for day, evs in by_date.items():
        evs.sort(key=lambda x: minutes(x["start"]))
        for a, b in zip(evs, evs[1:]):
            if minutes(b["start"]) < minutes(a["end"]):
                problems.append(f"  ! OVERLAP on {day}: '{a['title']}' and '{b['title']}'")
    return problems


# ---------- rendering ----------

def render(sched, all_events):
    cfg = sched["config"]
    cats = cfg["categories"]
    milestones = sched.get("milestones", [])
    goals = cfg.get("goals", [])

    dates = [d(e["date"]) for e in all_events] + [d(m["date"]) for m in milestones]
    lo, hi = min(dates), max(dates)

    # grid hour bounds: day window, auto-expanded to fit events
    h_start = minutes(cfg["day_window"]["start"]) // 60
    h_end = -(-minutes(cfg["day_window"]["end"]) // 60)
    for e in all_events:
        h_start = min(h_start, minutes(e["start"]) // 60)
        h_end = max(h_end, -(-minutes(e["end"]) // 60))
    col_h = (h_end - h_start) * PX_PER_HOUR

    # group into weeks
    ws = WEEK_START_INDEX[cfg.get("week_start", "sunday")[:3]]
    first = lo - timedelta(days=(lo.weekday() - ws) % 7)
    weeks = []
    w = first
    while w <= hi:
        weeks.append(w)
        w += timedelta(days=7)

    ev_by_date = {}
    for e in all_events:
        ev_by_date.setdefault(e["date"], []).append(e)
    ms_by_date = {}
    for m in milestones:
        ms_by_date.setdefault(m["date"], []).append(m)

    def goal_hours(g):
        return sum(
            (minutes(e["end"]) - minutes(e["start"])) / 60
            for e in all_events
            if e["category"] == g["category"] and d(g["start"]) <= d(e["date"]) <= d(g["end"])
        )

    week_html = []
    for wi, wstart in enumerate(weeks):
        days = [wstart + timedelta(days=i) for i in range(7)]
        wlabel = f"{days[0].strftime('%b %-d')} – {days[-1].strftime('%b %-d, %Y')}"

        # summary: hours per category this week
        cat_hours = {c: 0.0 for c in cats}
        for day in days:
            for e in ev_by_date.get(day.isoformat(), []):
                cat_hours[e["category"]] += (minutes(e["end"]) - minutes(e["start"])) / 60

        sum_items = "".join(
            f'<div class="sum-row"><span class="dot" style="background:{cats[c]["color"]}"></span>'
            f'<span class="sum-label">{esc(cats[c]["label"])}</span>'
            f'<span class="sum-val">{hours_fmt(h)} h</span></div>'
            for c, h in cat_hours.items() if h > 0
        ) or '<div class="sum-row sum-empty">No scheduled blocks this week.</div>'

        # goals overlapping this week
        goal_rows = []
        for g in goals:
            if d(g["end"]) < days[0] or d(g["start"]) > days[-1]:
                continue
            got = goal_hours(g)
            pct = min(100, round(100 * got / g["target_hours"])) if g["target_hours"] else 0
            color = cats.get(g["category"], {}).get("color", "#666")
            state = "goal-met" if got >= g["target_hours"] else ""
            goal_rows.append(
                f'<div class="goal {state}"><div class="goal-top"><span>{esc(g["label"])}</span>'
                f'<span class="goal-num">{hours_fmt(got)} / {hours_fmt(g["target_hours"])} h</span></div>'
                f'<div class="bar"><div class="bar-fill" style="width:{pct}%;background:{color}"></div></div></div>'
            )
        goals_html = "".join(goal_rows)

        # milestones this week
        ms_rows = "".join(
            f'<div class="ms-row"><span class="stamp">DUE</span>'
            f'<span><strong>{m_d.strftime("%a %b %-d")}</strong> — {esc(m["label"])}'
            + (f' <em class="ms-note">{esc(m["note"])}</em>' if m.get("note") else "")
            + "</span></div>"
            for m_d, m in sorted(
                (d(m["date"]), m) for day in days for m in ms_by_date.get(day.isoformat(), [])
            )
        )

        # day columns
        head_cells = ['<div class="gutter-head"></div>']
        body_cols = []
        hour_lines = "".join(
            f'<div class="hline" style="top:{(h - h_start) * PX_PER_HOUR}px"></div>'
            for h in range(h_start, h_end + 1)
        )
        gutter = "".join(
            f'<div class="hour" style="top:{(h - h_start) * PX_PER_HOUR}px">{fmt_hour(h)}</div>'
            for h in range(h_start, h_end + 1)
        )
        for day in days:
            iso = day.isoformat()
            dow = DOW[day.weekday()]
            off = dow in cfg.get("off_days", [])
            head_cells.append(
                f'<div class="day-head{" off" if off else ""}" data-date="{iso}">'
                f'<span class="dow">{day.strftime("%a")}</span>'
                f'<span class="dnum">{day.strftime("%-d")}</span>'
                + ("<span class=\"off-tag\">off</span>" if off else "")
                + "</div>"
            )
            blocks = []
            for m in ms_by_date.get(iso, []):
                blocks.append(
                    f'<div class="milestone" title="{esc(m.get("note", ""))}">'
                    f'<span class="stamp">DUE</span> {esc(m["label"])}</div>'
                )
            for e in sorted(ev_by_date.get(iso, []), key=lambda x: minutes(x["start"])):
                top = (minutes(e["start"]) - h_start * 60) * PX_PER_HOUR / 60
                hgt = (minutes(e["end"]) - minutes(e["start"])) * PX_PER_HOUR / 60
                color = cats[e["category"]]["color"]
                tip = " · ".join(
                    filter(None, [f'{fmt_time(e["start"])}–{fmt_time(e["end"])}',
                                  e.get("location"), e.get("notes")])
                )
                cls = "event" + (" tentative" if e.get("tentative") else "")
                if hgt < 44:
                    cls += " compact"
                meta = []
                if e.get("location"):
                    meta.append(esc(e["location"]))
                if e.get("tentative"):
                    meta.append("tentative")
                meta_html = f'<span class="ev-meta">{" · ".join(meta)}</span>' if meta and hgt >= 56 else ""
                blocks.append(
                    f'<div class="{cls}" style="top:{top:g}px;height:{hgt - 3:g}px;'
                    f'--c:{color}" title="{esc(tip)}">'
                    f'<span class="ev-time">{fmt_time(e["start"])}–{fmt_time(e["end"])}</span>'
                    f'<span class="ev-title">{esc(e["title"])}</span>{meta_html}</div>'
                )
            body_cols.append(
                f'<div class="day-col{" off" if off else ""}" data-date="{iso}" style="height:{col_h}px">'
                f"{hour_lines}{''.join(blocks)}"
                f'<div class="dim-overlay"></div><div class="now-line"></div></div>'
            )

        week_html.append(f"""
<section class="week" data-week="{wi}" data-start="{days[0].isoformat()}" data-end="{days[-1].isoformat()}" data-label="{esc(wlabel)}">
  <div class="panel">
    <div class="panel-col"><h2>Hours this week</h2>{sum_items}</div>
    <div class="panel-col panel-goals"><h2>Goals</h2>{goals_html or '<div class="sum-row sum-empty">No goals tracked in this window.</div>'}
      {f'<h2 class="ms-h">Deadlines</h2>{ms_rows}' if ms_rows else ''}</div>
  </div>
  <div class="grid">
    <div class="head-row">{''.join(head_cells)}</div>
    <div class="body-row">
      <div class="gutter" style="height:{col_h}px">{gutter}</div>
      {''.join(body_cols)}
    </div>
  </div>
</section>""")

    legend = "".join(
        f'<span class="lg"><span class="dot" style="background:{v["color"]}"></span>{esc(v["label"])}</span>'
        for v in cats.values()
    )

    h_start_js = h_start
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#150D2E">
<meta name="apple-mobile-web-app-title" content="Schedule">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="apple-touch-icon" href="icon.png">
<title>{esc(cfg['title'])}</title>
<style>
  :root {{
    --bg:#150D2E; --bg2:#1B1140; --panel:#1F1546; --line:#352765;
    --ink:#F3EDFF; --ink-soft:#A899D6; --grid-line:#2A1F56;
    --accent:#FF2E88; --cyan:#2DE2E6;
    --sunset:linear-gradient(90deg,#2DE2E6 0%,#6F8FD9 28%,#B967FF 52%,#FF2E88 76%,#FF9447 100%);
  }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{
    background:radial-gradient(1200px 600px at 75% -10%, #2B1A5E 0%, var(--bg) 55%) fixed, var(--bg);
    color:var(--ink);
    font:14px/1.45 -apple-system, "Segoe UI", system-ui, "Helvetica Neue", Arial, sans-serif;
    padding:28px clamp(14px, 3vw, 44px) 60px;
  }}
  header.mast {{ display:flex; align-items:baseline; gap:18px; flex-wrap:wrap; margin-bottom:2px; }}
  h1 {{
    font-family:Futura, "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
    font-size:26px; font-weight:700; letter-spacing:.22em; text-transform:uppercase;
    background:linear-gradient(90deg,#2DE2E6,#FF6EB3 70%);
    -webkit-background-clip:text; background-clip:text; color:transparent;
    filter:drop-shadow(0 0 14px rgba(255,46,136,.35));
  }}
  .horizon {{ height:3px; background:var(--sunset); border-radius:2px; margin:8px 0 12px;
    box-shadow:0 0 16px rgba(185,103,255,.45); }}
  .week-nav {{ display:flex; align-items:center; gap:10px; margin-left:auto; }}
  .week-nav button {{
    background:var(--panel); border:1px solid var(--line); border-radius:6px;
    padding:5px 12px; font:inherit; color:var(--ink); cursor:pointer;
  }}
  .week-nav button:hover {{ border-color:var(--cyan); box-shadow:0 0 8px rgba(45,226,230,.35); }}
  .week-nav button:focus-visible {{ outline:2px solid var(--cyan); outline-offset:1px; }}
  .week-nav button[disabled] {{ opacity:.3; cursor:default; box-shadow:none; }}
  #wk-label {{
    font-family:Futura, "Avenir Next", "Trebuchet MS", sans-serif;
    font-size:14px; letter-spacing:.12em; text-transform:uppercase;
    min-width:200px; text-align:center; color:var(--cyan);
  }}
  .legend {{ display:flex; gap:14px; flex-wrap:wrap; color:var(--ink-soft); font-size:12.5px; margin:0 0 18px; }}
  .lg {{ display:inline-flex; align-items:center; gap:6px; }}
  .dot {{ width:10px; height:10px; border-radius:3px; display:inline-block; flex:none;
    box-shadow:0 0 6px currentColor; }}

  .week {{ display:none; }}
  .week.active {{ display:block; }}

  .panel {{
    background:var(--panel); border:1px solid var(--line); border-radius:10px;
    padding:16px 20px; margin-bottom:16px; display:grid;
    grid-template-columns:minmax(220px,1fr) minmax(280px,1.6fr); gap:8px 36px;
  }}
  .panel h2 {{
    font-family:Futura, "Avenir Next", "Trebuchet MS", sans-serif;
    font-size:11px; text-transform:uppercase; letter-spacing:.18em;
    color:var(--cyan); font-weight:600; margin-bottom:8px;
  }}
  .ms-h {{ margin-top:14px; }}
  .sum-row {{ display:flex; align-items:center; gap:8px; padding:2.5px 0; font-size:13.5px; }}
  .sum-label {{ flex:1; }}
  .sum-val {{ font-variant-numeric:tabular-nums; color:var(--ink-soft); }}
  .sum-empty {{ color:var(--ink-soft); font-style:italic; }}
  .goal {{ margin-bottom:10px; }}
  .goal-top {{ display:flex; justify-content:space-between; gap:12px; font-size:13px; margin-bottom:4px; }}
  .goal-num {{ font-variant-numeric:tabular-nums; color:var(--ink-soft); white-space:nowrap; }}
  .goal-met .goal-num::after {{ content:" ✓"; color:#5BE3A9; }}
  .bar {{ height:7px; background:var(--grid-line); border-radius:4px; overflow:hidden; }}
  .bar-fill {{ height:100%; border-radius:4px; box-shadow:0 0 8px currentColor; }}
  .ms-row {{ display:flex; gap:10px; align-items:flex-start; font-size:13.5px; padding:3px 0; }}
  .ms-note {{ color:var(--ink-soft); font-style:italic; }}
  .stamp {{
    flex:none; font-size:10px; font-weight:700; letter-spacing:.14em; color:var(--accent);
    border:1.5px solid var(--accent); border-radius:3px; padding:1px 5px;
    transform:rotate(-4deg); display:inline-block;
    text-shadow:0 0 8px rgba(255,46,136,.6); box-shadow:0 0 8px rgba(255,46,136,.35);
  }}

  .grid {{ background:var(--bg2); border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  .head-row {{ display:grid; grid-template-columns:64px repeat(7, 1fr); }}
  .body-row {{ display:grid; grid-template-columns:64px repeat(7, 1fr); padding-bottom:16px; }}
  .day-head {{
    padding:10px 8px 8px; text-align:center; border-left:1px solid var(--line);
    display:flex; align-items:baseline; justify-content:center; gap:6px;
  }}
  .day-head .dow {{ font-size:11px; text-transform:uppercase; letter-spacing:.14em; color:var(--ink-soft); }}
  .day-head .dnum {{
    font-family:Futura, "Avenir Next", "Trebuchet MS", sans-serif;
    font-size:19px; font-weight:600;
  }}
  .day-head.today {{ box-shadow:inset 0 -3px 0 var(--cyan); }}
  .day-head.today .dow {{ color:var(--cyan); text-shadow:0 0 8px rgba(45,226,230,.6); }}
  .off-tag {{ font-size:10px; color:var(--ink-soft); border:1px solid var(--line); border-radius:3px; padding:0 4px; }}
  .gutter, .gutter-head {{ border-left:none; }}
  .gutter {{ position:relative; }}
  .hour {{
    position:absolute; right:8px; transform:translateY(-50%); font-size:11px;
    color:var(--ink-soft); font-variant-numeric:tabular-nums;
  }}
  .day-col {{ position:relative; border-left:1px solid var(--line); border-top:1px solid var(--line); }}
  .day-col.off {{ background:repeating-linear-gradient(-45deg,rgba(255,255,255,.035) 0 7px,transparent 7px 14px); }}
  .hline {{ position:absolute; left:0; right:0; border-top:1px solid var(--grid-line); }}
  .event {{
    position:absolute; left:4px; right:4px; border-radius:6px; padding:4px 7px;
    background:color-mix(in srgb, var(--c) 16%, var(--bg2));
    border-left:3.5px solid var(--c);
    box-shadow:0 0 10px color-mix(in srgb, var(--c) 22%, transparent);
    overflow:hidden; font-size:12px; line-height:1.3;
    display:flex; flex-direction:column;
  }}
  .event.tentative {{ border:1.5px dashed var(--c); border-left:3.5px solid var(--c); }}
  .event.compact {{ flex-direction:row; align-items:center; gap:6px; padding:1px 7px; white-space:nowrap; }}
  .event.compact .ev-title {{ overflow:hidden; text-overflow:ellipsis; font-size:11px; }}
  .event.compact .ev-time {{ flex:none; }}
  .ev-time {{ font-size:10.5px; color:var(--ink-soft); font-variant-numeric:tabular-nums; }}
  .ev-title {{ font-weight:600; color:color-mix(in srgb, var(--c) 70%, white); }}
  .ev-meta {{ font-size:10.5px; color:var(--ink-soft); }}
  .milestone {{
    position:absolute; top:2px; left:4px; right:4px; z-index:3;
    background:color-mix(in srgb, var(--accent) 14%, var(--bg2));
    border:1px solid var(--accent); border-radius:6px;
    padding:3px 7px; font-size:11.5px; font-weight:600; color:#FF8FC2;
    box-shadow:0 0 10px rgba(255,46,136,.35);
  }}
  .dim-overlay {{
    position:absolute; left:0; right:0; top:0; height:0; z-index:2;
    background:rgba(13,8,30,.55); pointer-events:none;
  }}
  .now-line {{
    position:absolute; left:0; right:0; display:none; z-index:4;
    border-top:2px solid var(--cyan); pointer-events:none;
    box-shadow:0 0 8px rgba(45,226,230,.7);
  }}
  .now-line::before {{
    content:""; position:absolute; left:-1px; top:-4.5px;
    width:7px; height:7px; border-radius:50%; background:var(--cyan);
    box-shadow:0 0 8px var(--cyan);
  }}
  footer {{ margin-top:14px; color:var(--ink-soft); font-size:12px; }}
  footer code {{ color:#CBBFF2; }}
  @media (max-width:820px) {{
    .panel {{ grid-template-columns:1fr; }}
    body {{ padding:16px 8px 40px; }}
    .ev-meta {{ display:none; }}
  }}
  @media print {{
    body {{ padding:0; background:white; color:#1a1a1a; }}
    .week-nav, footer, .horizon {{ display:none; }}
    h1 {{ -webkit-text-fill-color:#1a1a1a; color:#1a1a1a; background:none; filter:none; }}
    .grid, .panel {{ background:white; border-color:#bbb; break-inside:avoid; }}
    .panel h2, #wk-label {{ color:#444; }}
    .sum-val, .goal-num, .ms-note, .ev-time, .ev-meta, .hour,
    .day-head .dow, .off-tag, .sum-empty {{ color:#555; }}
    .day-col, .day-head {{ border-color:#ddd; }}
    .hline {{ border-color:#eee; }}
    .event {{ background:white; box-shadow:none; border:1px solid var(--c); border-left:3.5px solid var(--c); }}
    .ev-title {{ color:#1a1a1a; }}
    .milestone {{ background:white; box-shadow:none; }}
    .dim-overlay, .now-line {{ display:none; }}
  }}
  @media (prefers-reduced-motion: no-preference) {{
    .week.active {{ animation:fade .18s ease; }}
    @keyframes fade {{ from {{ opacity:.4 }} to {{ opacity:1 }} }}
  }}
</style>
</head>
<body>
<header class="mast">
  <h1>{esc(cfg['title'])}</h1>
  <nav class="week-nav" aria-label="Week navigation">
    <button id="prev" aria-label="Previous week">‹ Prev</button>
    <span id="wk-label"></span>
    <button id="next" aria-label="Next week">Next ›</button>
  </nav>
</header>
<div class="horizon"></div>
<div class="legend">{legend}</div>
{''.join(week_html)}
<footer>Generated from <code>data/schedule.json</code> + <code>data/recurring.json</code> by <code>build.py</code> — edit the data, not this file.</footer>
<script>
(function () {{
  var H_START = {h_start_js}, PX = {PX_PER_HOUR};
  var weeks = Array.prototype.slice.call(document.querySelectorAll('.week'));
  var label = document.getElementById('wk-label');
  var prev = document.getElementById('prev'), next = document.getElementById('next');
  function todayISO() {{
    var n = new Date();
    return n.getFullYear() + '-' + String(n.getMonth() + 1).padStart(2, '0') + '-' + String(n.getDate()).padStart(2, '0');
  }}
  var cur = 0, t = todayISO();
  weeks.forEach(function (w, i) {{
    if (w.dataset.start <= t && t <= w.dataset.end) cur = i;
  }});
  if (t > weeks[weeks.length - 1].dataset.end) cur = weeks.length - 1;
  function show(i) {{
    cur = Math.max(0, Math.min(weeks.length - 1, i));
    weeks.forEach(function (w, j) {{ w.classList.toggle('active', j === cur); }});
    label.textContent = weeks[cur].dataset.label;
    prev.disabled = cur === 0;
    next.disabled = cur === weeks.length - 1;
  }}
  prev.onclick = function () {{ show(cur - 1); }};
  next.onclick = function () {{ show(cur + 1); }};
  document.addEventListener('keydown', function (e) {{
    if (e.key === 'ArrowLeft') show(cur - 1);
    if (e.key === 'ArrowRight') show(cur + 1);
  }});
  function paintTime() {{
    var iso = todayISO();
    var n = new Date();
    var mins = n.getHours() * 60 + n.getMinutes();
    var y = (mins - H_START * 60) * PX / 60;
    document.querySelectorAll('.day-head').forEach(function (h) {{
      h.classList.toggle('today', h.dataset.date === iso);
    }});
    document.querySelectorAll('.day-col').forEach(function (col) {{
      var dim = col.querySelector('.dim-overlay');
      var line = col.querySelector('.now-line');
      var ch = col.offsetHeight;
      if (col.dataset.date < iso) {{
        dim.style.height = ch + 'px'; line.style.display = 'none';
      }} else if (col.dataset.date === iso) {{
        var yy = Math.max(0, Math.min(ch, y));
        dim.style.height = yy + 'px';
        line.style.display = (y > 0 && y < ch) ? 'block' : 'none';
        line.style.top = yy + 'px';
      }} else {{
        dim.style.height = '0'; line.style.display = 'none';
      }}
    }});
  }}
  show(cur);
  paintTime();
  setInterval(paintTime, 60000);
}})();
</script>
</body>
</html>
"""


def ics_escape(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def render_ics(sched, all_events):
    """Write schedule.ics — importable/subscribable in Apple Calendar, Google Calendar, etc.
    Floating local times; stable UIDs from event ids; fixed DTSTAMP keeps the build idempotent."""
    cats = sched["config"]["categories"]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//personal-schedule//build.py//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:" + ics_escape(sched["config"]["title"]),
    ]
    for e in sorted(all_events, key=lambda x: (x["date"], x["start"])):
        day = e["date"].replace("-", "")
        desc = "; ".join(filter(None, [
            cats.get(e["category"], {}).get("label", e["category"]),
            e.get("notes"),
            "tentative" if e.get("tentative") else None,
        ]))
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['id']}@personal-schedule",
            "DTSTAMP:20260101T000000Z",
            f"DTSTART:{day}T{e['start'].replace(':', '')}00",
            f"DTEND:{day}T{e['end'].replace(':', '')}00",
            "SUMMARY:" + ics_escape(e["title"]),
            "DESCRIPTION:" + ics_escape(desc),
        ]
        if e.get("location"):
            lines.append("LOCATION:" + ics_escape(e["location"]))
        if e.get("tentative"):
            lines.append("STATUS:TENTATIVE")
        lines.append("END:VEVENT")
    for m in sched.get("milestones", []):
        day = m["date"].replace("-", "")
        nxt = (d(m["date"]) + timedelta(days=1)).isoformat().replace("-", "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:milestone-{m['date']}@personal-schedule",
            "DTSTAMP:20260101T000000Z",
            f"DTSTART;VALUE=DATE:{day}",
            f"DTEND;VALUE=DATE:{nxt}",
            "SUMMARY:" + ics_escape("DUE: " + m["label"]),
            "DESCRIPTION:" + ics_escape(m.get("note", "")),
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    (ROOT / "schedule.ics").write_text("\r\n".join(lines) + "\r\n")


def main():
    sched, rec = load()
    cfg = sched["config"]
    events = list(sched.get("events", []))
    dates = [d(e["date"]) for e in events] + [d(m["date"]) for m in sched.get("milestones", [])]
    if not dates:
        sys.exit("No events or milestones in data/schedule.json — nothing to build.")
    expanded = expand_recurring(rec.get("rules", []), min(dates), max(dates), events)
    all_events = events + expanded

    problems = validate(all_events, cfg)
    print(f"Build: {len(events)} one-off events + {len(expanded)} recurring blocks "
          f"({min(dates)} → {max(dates)})")
    if problems:
        print("Validation notes:")
        print("\n".join(problems))
    else:
        print("Validation: clean — no overlaps, all categories known, all blocks inside the day window.")

    OUT.write_text(render(sched, all_events))
    render_ics(sched, all_events)
    print(f"Wrote {OUT}")
    print(f"Wrote {ROOT / 'schedule.ics'}")


if __name__ == "__main__":
    main()
