# Personal Schedule System

A living scheduling system. **The data is the product; the visual is a build artifact.**

```
/schedule
  /data
    schedule.json    ← THE source of truth (config, events, milestones, goals)
    recurring.json   ← repeating rules (workout, chores…), defined once
  index.html         ← generated week-view calendar — NEVER hand-edit
  build.py           ← regenerates index.html from /data (idempotent, stdlib only)
  README.md          ← this file
```

## The one rule

**Never edit `index.html`.** Edit the JSON in `/data`, then run:

```
python3 build.py
```

Running it twice produces identical output. It also validates as it builds and
prints warnings for overlapping events, unknown categories, or blocks outside
the day window. Fix data, rebuild, done. Open `index.html` by double-clicking —
no server, no internet needed.

## schedule.json

Three sections: `config`, `milestones`, `events`.

### Event schema

```json
{
  "id": "2026-06-15-internship",      // unique, stable; convention: date-slug
  "date": "2026-06-15",
  "start": "08:30",                   // 24h HH:MM
  "end": "11:00",
  "title": "Judicial Internship — meet Judge Goudie",
  "category": "internship",           // must exist in config.categories
  "location": "in person",            // optional
  "notes": "arrive by 8:30",          // optional, shows in hover tooltip
  "fixed": true,                      // optional, semantic flag
  "tentative": true,                  // optional → dashed border in the visual
  "replaces": "workout"               // optional → suppresses that recurring
}                                     //   rule on this date (one-off override)
```

### config

- `categories` — id → `{label, color}`. **Adding a new category (e.g. `class`,
  `travel`) = add one line here.** Nothing else changes; legend, colors, and
  summary pick it up automatically.
- `day_window` — default grid hours (currently 05:00–23:00). The grid auto-expands if an
  event falls outside it.
- `week_start` — `"sunday"` (or `"monday"`, etc.). Weeks paginate automatically.
- `off_days` — e.g. `["sat"]`; rendered hatched with an "off" tag.
- `goals` — general progress tracking, not hardcoded to anything:

```json
{ "id": "ra-prep-jun18", "label": "RA prep — 12-hr target…",
  "category": "ra", "target_hours": 12,
  "start": "2026-06-11", "end": "2026-06-17" }
```

A goal sums all hours of its `category` between `start` and `end` (inclusive),
even across week boundaries, and renders a progress bar on every week it
overlaps.

### milestones

```json
{ "date": "2026-06-18", "label": "RA Meeting", "note": "Time TBC…" }
```

Rendered as a red **DUE** stamp at the top of that day's column and listed
under "Deadlines" in the summary panel.

## recurring.json

Each rule expands into concrete blocks at build time, across the full date
range of the explicit events/milestones:

```json
{
  "id": "workout", "title": "Workout", "category": "workout",
  "days": ["sun","mon","tue","wed","thu","fri"],
  "start": "17:00", "end": "18:00",
  "day_overrides": { "sun": { "start": "16:30", "end": "18:00" } },
  "valid_from": "2026-06-11",        // optional; also "valid_until"
  "skip_dates": ["2026-07-04"]       // optional one-off cancellations
}
```

**Override precedence** (most specific wins):
1. An explicit event with `"replaces": "<rule_id>"` on a date → rule skipped there.
2. A date in `skip_dates` → rule skipped there.
3. `day_overrides` for that weekday → different time.
4. The rule's default `start`/`end`.

## Edit workflow (what to ask the agent)

Say it in plain language; the agent will restate the change, edit **data only**,
flag downstream effects (freed hours, goal shortfalls, conflicts), rebuild, and
summarize. Examples:

- "My Monday internship got moved to 10am."
- "I'm sick — clear Tuesday." *(expect a proposal for where the RA hours go)*
- "Move the Tuesday internship to Wednesday." *(it's flagged tentative for this)*
- "Add a recurring Tuesday class, 6–8pm, starting July 7." *(new rule + new `class` category)*

Standing constraints the agent respects: hardest work in the mornings,
Saturdays off, never sacrifice workouts to cram.

## Work cadence rule (standing)

Work (judicial internship) is in-person, **mornings only**, 2.5–3.5 hrs per
visit, **2–3 visits per week, alternating**: a 2-visit week is followed by a
3-visit week, and vice versa. This is a planning convention, not automated —
when planning a new week, count the prior week's visits and schedule the
opposite. Planned future visits are entered as `tentative: true` until the
specific days are confirmed. Current ledger: week of Jun 14 = 2 visits → week
of Jun 21 = 3 (Mon/Wed/Fri) → week of Jun 28 = 2 (Mon/Wed).

## Adding a future week

"Plan the week of June 22" →
1. New events appended to `schedule.json` (recurring rules apply automatically —
   no re-entry of workouts/chores).
2. Rebuild. Week navigation picks up the new week with zero structural changes.

## Designed-in growth (don't fight the model)

- New categories/goals/milestones: config-only edits.
- New recurring commitments: one rule in `recurring.json`.
- Future views (month, agenda, `.ics` export): the event schema already carries
  everything needed (stable ids, ISO dates, 24h times, categories) — a new view
  is just another render function in `build.py`, no data migration.
- Keep ids stable when editing an event in place; delete + re-add only when the
  thing itself changed identity.
