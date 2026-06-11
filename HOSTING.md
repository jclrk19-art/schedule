# Hosting on GitHub Pages (one-time setup ≈ 10 minutes)

The goal: a permanent URL for the visual, an app-style icon on your iPhone/iPad
home screen, and a live calendar subscription that updates itself.

## One-time setup (do this on a computer — easier than on the phone)

1. **Create a GitHub account** at github.com (free) if you don't have one.
2. **Create the repository:** click **+ → New repository**. Name it `schedule`,
   set it to **Public**, check **"Add a README file"**, click **Create repository**.
3. **Upload the files:** in the new repo, click **Add file → Upload files** and
   drag in everything from this folder — `index.html`, `schedule.ics`,
   `icon.png`, `build.py`, `README.md`, `HOSTING.md`, and the `data` folder
   (dragging the folder itself preserves the structure in Chrome/Edge).
   Click **Commit changes**.
4. **Turn on Pages:** repo **Settings → Pages** (left sidebar) →
   under "Build and deployment", Source = **Deploy from a branch**,
   Branch = **main**, folder = **/ (root)** → **Save**.
5. Wait ~1 minute, refresh the Pages settings page, and your URL appears:

   ```
   https://YOUR-USERNAME.github.io/schedule/
   ```

## On your iPhone / iPad

- **The visual as an app:** open the URL in Safari → **Share → Add to Home
  Screen**. You get a retro-sunset icon that opens straight into the schedule,
  full screen, themed to match.
- **Live Apple Calendar subscription:** Settings → **Apps → Calendar →
  Calendar Accounts → Add Account → Other → Add Subscribed Calendar**, and
  enter:

  ```
  https://YOUR-USERNAME.github.io/schedule/schedule.ics
  ```

  iOS refreshes subscribed calendars automatically — no re-importing, ever.

## Update workflow (after every change)

1. Tell the agent the change → it edits the data, rebuilds, and hands you the
   updated files (at minimum `index.html` and `schedule.ics`; also any changed
   `data/*.json` so the repo stays the source of truth).
2. In the repo: **Add file → Upload files**, drag the updated files in,
   **Commit changes**. Same filenames = clean replacement.
3. Pages redeploys itself in ~1 minute. The home-screen app shows the new
   version on next open; the subscribed calendar picks it up on its next
   automatic refresh.

## One honest caveat

A public repo means the schedule is visible to anyone who has the URL (it's
obscure, but it is public). Keep anything sensitive out of event titles/notes,
or ask the agent to generalize labels. GitHub only offers Pages on private
repos with a paid plan; that's the upgrade path if you ever want it locked down.
