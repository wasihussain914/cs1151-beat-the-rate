# Beat the Rate 📦

In-class game for the CS 1151 Team 8 presentation (A Gift of Fire, Ch. 6 — Work).
Players are warehouse "associates" tapping packages while an invisible productivity
quota ratchets to 80% of the fastest player's pace. Three rounds, then a corporate
restructuring lays off the bottom half. The algorithm is rigged on purpose — that's
the lesson.

**Live:**
- Player: https://wasihussain.com/cs1151
- Host/projector: `host.html?key=...` (ask Wasi for the key — keep it out of this repo)

## How it works

- `web/index.html` — player page (join → tap packages → get terminated). Static, no build step.
- `web/host.html` — projector view: QR, leaderboard, round controls (R1 classic / R2 bombs / R3 visible-quota), termination feed, 📉 Restructure finale.
- `server/cs1151_game.py` — Flask blueprint, all state in memory. Endpoints under `/cs1151/`:
  `join`, `beat` (heartbeat w/ picks+strikes), `state`, `start` (host key), `layoff` (host key, only after a round ends), `reset` (host key).

Game rules live at the top of `cs1151_game.py` (round length, ratchet %, grace period, layoff score penalties).

## Deploys (important!)

This repo is the editable copy for the team. Production runs elsewhere:
- `web/*` is served from the `cs1151/` folder of the `wasihussain914/portfolio` repo (GitHub Pages).
- `server/cs1151_game.py` runs on Wasi's always-on box behind `admin.wasihussain.com`.

So: make changes here via PR → Wasi (or Chopper) syncs them to production. Don't edit
the API base URLs in the HTML unless you're running your own backend locally.

## Local dev

```bash
pip install flask
python -m flask --app server/dev_app run -p 8787
# then open web/index.html and change const API to http://127.0.0.1:8787/cs1151
```

