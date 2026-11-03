"""CS 1151 'Beat the Rate' — in-class warehouse clicker game (Team 8 presentation, Nov 3 2026).

Open (no-login) API under /cs1151/*. All state is in-memory; nothing persists.
Players: static pages on wasihussain.com/cs1151 talk to this via CORS.
Host controls require the key in dashboard/data/cs1151_key.txt.

Round modes:
  classic  - R1 "First Shift": quota hidden from players, ratchets to 80% of top rate.
  bombs    - R2 "Peak Season": bombs spawn among packages; taps are logged as injuries.
  visible  - R3 "Glass Warehouse": same as classic but quota shown to players.

NOBODY is fired mid-round. The system silently accumulates a record per player
across all rounds: picks, rate violations (below quota after grace), injuries.
After the final round the host POSTs /layoff: the bottom half of everyone who
played — ranked by total picks minus penalties — is terminated at once
(reason: restructuring). One big cull, projector moment, debrief.
"""
import time, secrets
from pathlib import Path
from flask import Blueprint, request, jsonify

bp = Blueprint("cs1151", __name__, url_prefix="/cs1151")

KEY_FILE = Path(__file__).resolve().parent / "data" / "cs1151_key.txt"
ALLOWED_ORIGINS = {"https://wasihussain.com", "http://localhost:8787", "http://127.0.0.1:8787"}

ROUND_SECS = 90
START_RATE = 20.0          # picks/min required at kickoff
RATCHET_SECS = 10
RATCHET_FRACTION = 0.80
GRACE_SECS = 20
WINDOW_SECS = 15           # rolling window for a player's rate

INJURY_PENALTY = 15        # layoff score: picks minus penalties
VIOLATION_PENALTY = 5

MODES = {"classic", "bombs", "visible"}

G = {"round": None, "players": {}, "laid_off": []}


def _host_key():
    if not KEY_FILE.exists():
        KEY_FILE.write_text(secrets.token_urlsafe(12))
    return KEY_FILE.read_text().strip()


def _now():
    return time.time()


def _rate(p, now):
    """Picks/min over the trailing window."""
    hist = p["history"]
    if len(hist) < 2:
        return 0.0
    cutoff = now - WINDOW_SECS
    base = hist[0]
    for h in hist:
        if h[0] <= cutoff:
            base = h
        else:
            break
    dt = max(hist[-1][0] - base[0], 1e-6)
    if now - hist[-1][0] > 6:        # stale client: count the silence
        dt += now - hist[-1][0]
    return max(0.0, (hist[-1][1] - base[1]) / dt * 60.0)


def _evaluate():
    """Advance ratchet + log violations. Nobody is fired here."""
    r = G["round"]
    now = _now()
    if not r or r["over"]:
        return
    if now - r["started"] >= ROUND_SECS:
        r["over"] = True
        return
    alive = [p for p in G["players"].values() if p["status"] == "alive"]
    rates = {id(p): _rate(p, now) for p in alive}
    if now - r["last_ratchet"] >= RATCHET_SECS and rates:
        top = max(rates.values())
        r["required"] = max(r["required"], top * RATCHET_FRACTION)
        r["last_ratchet"] = now
    if now - r["started"] > GRACE_SECS and now - r["last_check"] >= 3:
        r["last_check"] = now
        for p in alive:
            if rates[id(p)] < r["required"]:
                p["violations"] += 1


def _score(p):
    """Layoff ranking: total output minus safety/benchmark penalties."""
    return (p["total_picks"] + p["picks"]
            - INJURY_PENALTY * (p["total_strikes"] + p["bomb_strikes"])
            - VIOLATION_PENALTY * p["violations"])


def _public_state():
    r = G["round"]
    now = _now()
    players = sorted(G["players"].values(), key=lambda p: -p["picks"])
    req = r["required"] if r else START_RATE
    return {
        "round_secs": ROUND_SECS,
        "running": bool(r) and not r["over"],
        "over": bool(r) and r["over"],
        "mode": r["mode"] if r else None,
        "time_left": max(0, int(r["started"] + ROUND_SECS - now)) if r else ROUND_SECS,
        "required": round(req, 1),
        "players": [{"name": p["name"], "picks": p["picks"],
                     "total": p["total_picks"] + p["picks"],
                     "rate": round(_rate(p, now), 1), "status": p["status"],
                     "reason": p.get("reason"),
                     "strikes": p["total_strikes"] + p["bomb_strikes"],
                     "violations": p["violations"],
                     "flagged": bool(r) and not r["over"] and p["status"] == "alive"
                                and _rate(p, now) < req and (now - r["started"]) > GRACE_SECS,
                     "fired_at": p.get("fired_at")} for p in players],
        "fired_order": r["fired_order"] if r else [],
        "laid_off": G["laid_off"],
        "alive": sum(1 for p in G["players"].values() if p["status"] == "alive"),
        "total": len(G["players"]),
    }


@bp.after_request
def cors(resp):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@bp.route("/join", methods=["POST", "OPTIONS"])
def join():
    if request.method == "OPTIONS":
        return "", 204
    name = (request.get_json(silent=True) or {}).get("name", "").strip()[:20]
    if not name:
        return jsonify(ok=False, error="name required"), 400
    pid = secrets.token_urlsafe(8)
    G["players"][pid] = {"name": name, "picks": 0, "history": [], "status": "alive",
                         "bomb_strikes": 0, "violations": 0,
                         "total_picks": 0, "total_strikes": 0}
    return jsonify(ok=True, player_id=pid)


@bp.route("/beat", methods=["POST", "OPTIONS"])
def beat():
    if request.method == "OPTIONS":
        return "", 204
    d = request.get_json(silent=True) or {}
    p = G["players"].get(d.get("player_id", ""))
    if not p:
        return jsonify(ok=False, error="unknown player"), 404
    r = G["round"]
    p["picks"] = max(p["picks"], int(d.get("picks", 0)))
    p["history"].append((_now(), p["picks"]))
    p["history"] = p["history"][-60:]
    if r and not r["over"] and r["mode"] == "bombs":
        p["bomb_strikes"] = max(p["bomb_strikes"], int(d.get("strikes", 0)))
    _evaluate()
    s = _public_state()
    return jsonify(ok=True, status=p["status"], reason=p.get("reason"),
                   round_secs=ROUND_SECS,
                   required=s["required"], mode=s["mode"], strikes=p["bomb_strikes"],
                   time_left=s["time_left"], running=s["running"], over=s["over"],
                   alive=s["alive"], total=s["total"])


@bp.route("/state")
def state():
    _evaluate()
    return jsonify(_public_state())


@bp.route("/start", methods=["POST", "OPTIONS"])
def start():
    if request.method == "OPTIONS":
        return "", 204
    d = request.get_json(silent=True) or {}
    if d.get("key") != _host_key():
        return jsonify(ok=False), 403
    mode = d.get("mode", "classic")
    if mode not in MODES:
        return jsonify(ok=False, error="bad mode"), 400
    now = _now()
    for p in G["players"].values():
        # bank this round's record, then reset round-local fields
        p["total_picks"] += p["picks"]
        p["total_strikes"] += p["bomb_strikes"]
        p.update(picks=0, history=[], bomb_strikes=0, status="alive")
        p.pop("reason", None)
        p.pop("fired_at", None)
    G["laid_off"] = []   # a new round revives everyone (recovers from accidental layoffs)
    G["round"] = {"started": now, "required": START_RATE, "last_ratchet": now,
                  "last_check": now, "over": False, "fired_order": [], "mode": mode}
    return jsonify(ok=True, mode=mode)


@bp.route("/layoff", methods=["POST", "OPTIONS"])
def layoff():
    """Finale after all rounds: cull the bottom half of EVERYONE who played,
    ranked by cumulative picks minus injury/benchmark penalties."""
    if request.method == "OPTIONS":
        return "", 204
    if (request.get_json(silent=True) or {}).get("key") != _host_key():
        return jsonify(ok=False), 403
    r = G["round"]
    _evaluate()
    if r and not r["over"]:
        return jsonify(ok=False, error="round still running"), 409
    alive = sorted([p for p in G["players"].values() if p["status"] == "alive"],
                   key=_score)
    cut = alive[:len(alive) // 2] if len(alive) > 1 else []
    for p in cut:
        p["status"] = "terminated"
        p["reason"] = "restructuring"
        p["fired_at"] = None
        if r is not None:
            r["fired_order"].append({"name": p["name"], "reason": "restructuring"})
    G["laid_off"] = [p["name"] for p in cut]
    return jsonify(ok=True, laid_off=G["laid_off"], remaining=len(alive) - len(cut))


@bp.route("/reset", methods=["POST", "OPTIONS"])
def reset():
    if request.method == "OPTIONS":
        return "", 204
    if (request.get_json(silent=True) or {}).get("key") != _host_key():
        return jsonify(ok=False), 403
    G["round"] = None
    G["players"].clear()
    G["laid_off"] = []
    return jsonify(ok=True)
