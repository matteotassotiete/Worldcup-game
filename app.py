import os
import random
import string
from datetime import datetime, timezone, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")

def utc_to_local_date(utc_str):
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

from db import get_db, init_db

from bracket_skeleton import (ROUNDS, ROUND_ORDER, ROUND_LABELS, FEEDS, NEXT_SLOT,
                              predicted_sets_from_picks)
from bracket_core import (get_state, effective_status, is_open_for_writes,
                          advancing_team, get_bracket_matches, actual_sets,
                          SCORE_ROUND_SOURCE)
from bracket_scoring import BRACKET_POINTS, BRACKET_ROUNDS, round_max, grand_total_max

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

# Tournament picks lock: June 11 2026 at 11:00 UTC (8h before first kickoff)
PICKS_LOCK_UTC = datetime(2026, 6, 11, 11, 0, 0, tzinfo=timezone.utc)

# Admin gate for /admin/bracket. Must be set in .env to use the admin page.
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")


# ── Context processor — inject nav groups into every template ────────────────

@app.context_processor
def inject_nav_groups():
    if "user_id" not in session:
        return {}
    try:
        db = get_request_db()
        groups = db.execute("""
            SELECT g.* FROM groups g
            JOIN group_members gm ON gm.group_id=g.id
            WHERE gm.user_id=%s ORDER BY g.name
        """, (session["user_id"],)).fetchall()
        ctx = {"nav_groups": groups}
        try:
            state = get_state(db)
            ctx["bracket_status"] = effective_status(state)
            ctx["bracket_open_at"] = state["open_at"]
        except Exception:
            ctx["bracket_status"] = None
        return ctx
    except Exception:
        return {"nav_groups": []}


# ── DB connection per request ─────────────────────────────────────────────────

def get_request_db():
    if "_db" not in g:
        g._db = get_db()
    return g._db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("_db", None)
    if db is not None:
        db.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    if "user_id" not in session:
        return None
    db = get_request_db()
    return db.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],)).fetchone()


def tournament_locked():
    return datetime.now(timezone.utc) >= PICKS_LOCK_UTC


def generate_group_code():
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(random.choices(chars, k=6))
        db = get_request_db()
        existing = db.execute("SELECT id FROM groups WHERE code=%s", (code,)).fetchone()
        if not existing:
            return code


def prediction_is_open(kickoff_utc_str):
    kickoff = datetime.fromisoformat(kickoff_utc_str.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) < kickoff - timedelta(minutes=10)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("predict"))
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        team_name = request.form.get("team_name", "").strip()
        pin = request.form.get("pin", "").strip()

        if not team_name or len(team_name) < 2:
            flash("Team name must be at least 2 characters.")
            return render_template("signup.html")
        if not pin.isdigit() or len(pin) != 4:
            flash("PIN must be exactly 4 digits.")
            return render_template("signup.html")

        pin_hash = generate_password_hash(pin)
        db = get_request_db()
        try:
            user_id = db.insert_returning_id(
                "INSERT INTO users (team_name, pin_hash) VALUES (%s, %s) RETURNING id",
                (team_name, pin_hash)
            )
            db.commit()
            session["user_id"] = user_id
            session["team_name"] = team_name
            return redirect(url_for("group"))
        except Exception:
            db._conn.rollback() if hasattr(db, '_conn') else None
            flash("That team name is already taken.")
            return render_template("signup.html")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        team_name = request.form.get("team_name", "").strip()
        pin = request.form.get("pin", "").strip()

        db = get_request_db()
        user = db.execute(
            "SELECT * FROM users WHERE LOWER(team_name)=LOWER(%s)", (team_name,)
        ).fetchone()

        if not user or not check_password_hash(user["pin_hash"], pin):
            flash("Invalid team name or PIN.")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["team_name"] = user["team_name"]
        return redirect(url_for("predict"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/group", methods=["GET", "POST"])
@login_required
def group():
    if request.method == "POST":
        action = request.form.get("action")
        db = get_request_db()
        user_id = session["user_id"]

        if action == "create":
            name = request.form.get("group_name", "").strip()
            if not name:
                flash("Group name required.")
                return render_template("group.html")
            code = generate_group_code()
            group_id = db.insert_returning_id(
                "INSERT INTO groups (name, code) VALUES (%s, %s) RETURNING id",
                (name, code)
            )
            db.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
                       (group_id, user_id))
            db.commit()
            return render_template("group.html", created_code=code, created_name=name)

        elif action == "join":
            code = request.form.get("code", "").strip().upper()
            grp = db.execute("SELECT * FROM groups WHERE code=%s", (code,)).fetchone()
            if not grp:
                flash("Group not found. Check the code.")
                return render_template("group.html")
            try:
                db.execute("INSERT INTO group_members (group_id, user_id) VALUES (%s, %s)",
                           (grp["id"], user_id))
                db.commit()
                flash(f"Joined group \"{grp['name']}\"!")
            except Exception:
                flash(f"You're already in \"{grp['name']}\".")
            return render_template("group.html")

    return render_template("group.html")


@app.route("/picks", methods=["GET", "POST"])
@login_required
def picks():
    locked = tournament_locked()
    db = get_request_db()
    user = get_current_user()

    if request.method == "POST":
        if locked:
            flash("Tournament has started — picks are locked.")
            return redirect(url_for("picks"))
        champion = request.form.get("champion_pick", "").strip()
        top_scorer = request.form.get("top_scorer_pick", "").strip()
        db.execute(
            "UPDATE users SET champion_pick=%s, top_scorer_pick=%s WHERE id=%s",
            (champion or None, top_scorer or None, session["user_id"])
        )
        db.commit()
        flash("Picks saved!")
        return redirect(url_for("picks"))

    teams = set()
    for row in db.execute("SELECT home_team, away_team FROM matches").fetchall():
        teams.add(row["home_team"])
        teams.add(row["away_team"])
    teams = sorted(teams)

    return render_template("picks.html", user=user, teams=teams, locked=locked)


@app.route("/rules")
@login_required
def rules():
    return render_template("rules.html")


@app.route("/predict")
@login_required
def predict():
    from collections import defaultdict
    db = get_request_db()
    user_id = session["user_id"]

    matches = db.execute("SELECT * FROM matches ORDER BY kickoff_utc").fetchall()

    preds = {row["match_id"]: row for row in db.execute(
        "SELECT * FROM predictions WHERE user_id=%s", (user_id,)
    ).fetchall()}

    settled_map = {}
    if preds:
        pred_ids = list(preds.keys())
        placeholders = ",".join(["%s"] * len(pred_ids))
        for row in db.execute(
            f"SELECT s.*, p.match_id FROM settlements s "
            f"JOIN predictions p ON p.id=s.prediction_id "
            f"WHERE p.user_id=%s AND p.match_id IN ({placeholders})",
            [user_id] + pred_ids
        ).fetchall():
            settled_map[row["match_id"]] = row

    open_map = {m["id"]: prediction_is_open(m["kickoff_utc"]) for m in matches}

    # Group by local (Pacific) date
    by_date = defaultdict(list)
    for m in matches:
        by_date[utc_to_local_date(m["kickoff_utc"])].append(m)
    dates = sorted(by_date.keys())

    # Per-date summary for tab badges
    date_summary = {}
    for date in dates:
        pts = sum(settled_map[m["id"]]["total_points"]
                  for m in by_date[date]
                  if m["settled"] and m["id"] in settled_map)
        settled_n = sum(1 for m in by_date[date] if m["settled"])
        open_n = sum(1 for m in by_date[date] if open_map[m["id"]])
        predicted_n = sum(1 for m in by_date[date] if m["id"] in preds)
        date_summary[date] = {"pts": pts, "settled": settled_n,
                               "open": open_n, "predicted": predicted_n,
                               "count": len(by_date[date])}

    # Overall user stats
    total_pts = sum(s["total_points"] for s in settled_map.values())
    exacts = sum(1 for s in settled_map.values() if s["base_points"] == 100)

    return render_template("predict.html",
                           matches=matches,
                           by_date=by_date,
                           dates=dates,
                           date_summary=date_summary,
                           preds=preds,
                           settled_map=settled_map,
                           open_map=open_map,
                           total_pts=total_pts,
                           exacts=exacts,
                           today=datetime.now(LOCAL_TZ).strftime("%Y-%m-%d"))


@app.route("/api/predict", methods=["POST"])
@login_required
def api_predict():
    data = request.get_json()
    match_id = data.get("match_id")
    try:
        home_pred = int(data.get("home_pred"))
        away_pred = int(data.get("away_pred"))
    except (TypeError, ValueError):
        return jsonify({"error": "Scores must be integers."}), 400

    if not (0 <= home_pred <= 15 and 0 <= away_pred <= 15):
        return jsonify({"error": "Scores must be 0–15."}), 400

    db = get_request_db()
    match = db.execute("SELECT * FROM matches WHERE id=%s", (match_id,)).fetchone()
    if not match:
        return jsonify({"error": "Match not found."}), 404

    if not prediction_is_open(match["kickoff_utc"]):
        return jsonify({"error": "Predictions are locked for this match."}), 403

    user_id = session["user_id"]
    now = datetime.now(timezone.utc).isoformat()
    db.execute("""
        INSERT INTO predictions (user_id, match_id, home_pred, away_pred, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(user_id, match_id) DO UPDATE SET
            home_pred=EXCLUDED.home_pred,
            away_pred=EXCLUDED.away_pred,
            updated_at=EXCLUDED.updated_at
    """, (user_id, match_id, home_pred, away_pred, now))
    db.commit()
    return jsonify({"ok": True})


@app.route("/leaderboard")
@login_required
def leaderboard():
    db = get_request_db()
    user_id = session["user_id"]

    user_groups = db.execute("""
        SELECT g.* FROM groups g
        JOIN group_members gm ON gm.group_id=g.id
        WHERE gm.user_id=%s
        ORDER BY g.name
    """, (user_id,)).fetchall()

    selected_group = request.args.get("group", "everyone")

    def get_standings(group_id=None):
        if group_id:
            return db.execute("""
                SELECT u.id, u.team_name,
                    COALESCE(SUM(s.total_points), 0)
                    + COALESCE(MAX(ta.champion_points), 0)
                    + COALESCE(MAX(ta.top_scorer_points), 0) AS total_points,
                    COUNT(CASE WHEN s.base_points=100 THEN 1 END) AS exacts,
                    COUNT(p.id) AS predictions_made,
                    COUNT(s.id) AS settled_preds,
                    CASE WHEN COUNT(s.id) > 0
                         THEN ROUND(CAST(COALESCE(SUM(s.total_points), 0) AS NUMERIC) / COUNT(s.id), 1)
                         ELSE NULL END AS pts_per_pred
                FROM users u
                JOIN group_members gm ON gm.user_id=u.id AND gm.group_id=%s
                LEFT JOIN predictions p ON p.user_id=u.id
                LEFT JOIN settlements s ON s.prediction_id=p.id
                LEFT JOIN tournament_awards ta ON ta.user_id=u.id
                GROUP BY u.id, u.team_name
                ORDER BY total_points DESC, exacts DESC
            """, (group_id,)).fetchall()
        else:
            return db.execute("""
                SELECT u.id, u.team_name,
                    COALESCE(SUM(s.total_points), 0)
                    + COALESCE(MAX(ta.champion_points), 0)
                    + COALESCE(MAX(ta.top_scorer_points), 0) AS total_points,
                    COUNT(CASE WHEN s.base_points=100 THEN 1 END) AS exacts,
                    COUNT(p.id) AS predictions_made,
                    COUNT(s.id) AS settled_preds,
                    CASE WHEN COUNT(s.id) > 0
                         THEN ROUND(CAST(COALESCE(SUM(s.total_points), 0) AS NUMERIC) / COUNT(s.id), 1)
                         ELSE NULL END AS pts_per_pred
                FROM users u
                LEFT JOIN predictions p ON p.user_id=u.id
                LEFT JOIN settlements s ON s.prediction_id=p.id
                LEFT JOIN tournament_awards ta ON ta.user_id=u.id
                GROUP BY u.id, u.team_name
                ORDER BY total_points DESC, exacts DESC
            """).fetchall()

    selected_group_obj = None
    if selected_group == "everyone":
        standings = get_standings()
    else:
        try:
            gid = int(selected_group)
            standings = get_standings(gid)
            selected_group_obj = next((g for g in user_groups if g["id"] == gid), None)
        except ValueError:
            standings = get_standings()

    return render_template("leaderboard.html",
                           user_groups=user_groups,
                           standings=standings,
                           selected_group=selected_group,
                           selected_group_obj=selected_group_obj,
                           current_user_id=user_id)


@app.route("/team/<int:team_user_id>")
@login_required
def team_profile(team_user_id):
    from collections import defaultdict
    db = get_request_db()

    team = db.execute("SELECT id, team_name FROM users WHERE id=%s", (team_user_id,)).fetchone()
    if not team:
        flash("Team not found.")
        return redirect(url_for("leaderboard"))

    # Only settled matches — never reveal future predictions
    matches = db.execute(
        "SELECT * FROM matches WHERE settled=1 ORDER BY kickoff_utc"
    ).fetchall()

    if not matches:
        return render_template("team.html", team=team, by_date={}, dates=[], total_pts=0, exacts=0)

    match_ids = [m["id"] for m in matches]
    placeholders = ",".join(["%s"] * len(match_ids))

    preds = {row["match_id"]: row for row in db.execute(
        f"SELECT * FROM predictions WHERE user_id=%s AND match_id IN ({placeholders})",
        [team_user_id] + match_ids
    ).fetchall()}

    settled_map = {}
    if preds:
        pred_ids = list(preds.keys())
        ph2 = ",".join(["%s"] * len(pred_ids))
        for row in db.execute(
            f"SELECT s.*, p.match_id FROM settlements s "
            f"JOIN predictions p ON p.id=s.prediction_id "
            f"WHERE p.user_id=%s AND p.match_id IN ({ph2})",
            [team_user_id] + pred_ids
        ).fetchall():
            settled_map[row["match_id"]] = row

    by_date = defaultdict(list)
    for m in matches:
        by_date[utc_to_local_date(m["kickoff_utc"])].append(m)
    dates = sorted(by_date.keys())

    total_pts = sum(s["total_points"] for s in settled_map.values())
    exacts = sum(1 for s in settled_map.values() if s["base_points"] == 100)

    return render_template("team.html",
                           team=team,
                           by_date=by_date,
                           dates=dates,
                           preds=preds,
                           settled_map=settled_map,
                           total_pts=total_pts,
                           exacts=exacts)


@app.route("/api/match/<int:match_id>/predictions")
@login_required
def match_predictions(match_id):
    db = get_request_db()
    match = db.execute(
        "SELECT * FROM matches WHERE id=%s AND settled=1", (match_id,)
    ).fetchone()
    if not match:
        return jsonify({"error": "Match not found or not settled"}), 404

    rows = db.execute("""
        SELECT u.id AS user_id, u.team_name,
               p.home_pred, p.away_pred,
               COALESCE(s.total_points, 0) AS total_points,
               COALESCE(s.base_points, 0) AS base_points,
               COALESCE(s.bonus_labels, '') AS bonus_labels
        FROM predictions p
        JOIN users u ON u.id = p.user_id
        LEFT JOIN settlements s ON s.prediction_id = p.id
        WHERE p.match_id = %s
        ORDER BY COALESCE(s.total_points, 0) DESC, u.team_name
    """, (match_id,)).fetchall()

    return jsonify({
        "match": {
            "home_team": match["home_team"],
            "away_team": match["away_team"],
            "home_score": match["home_score"],
            "away_score": match["away_score"],
        },
        "predictions": [dict(r) for r in rows],
        "current_user_id": session["user_id"]
    })


# ── Bracket Game ────────────────────────────────────────────────────────────

def _user_bracket_picks(db, user_id):
    rows = db.execute(
        "SELECT match_id, picked_team FROM bracket_picks WHERE user_id=%s", (user_id,)
    ).fetchall()
    return {r["match_id"]: r["picked_team"] for r in rows}


def _compute_slot_teams(matches_by_id, picks):
    """The two teams shown in each slot. R32 from seeded matchups; later rounds
    derived from the user's own upstream picks (the predicted bracket)."""
    slot_teams = {}
    for mid in ROUNDS["R32"]:
        m = matches_by_id.get(mid)
        slot_teams[mid] = [m["home_team"] if m else None,
                           m["away_team"] if m else None]
    for rk in ["R16", "QF", "SF", "FINAL"]:
        for mid in ROUNDS[rk]:
            h_src, a_src = FEEDS[mid]
            slot_teams[mid] = [picks.get(h_src), picks.get(a_src)]
    return slot_teams


def _revalidate_picks(db, user_id):
    """Delete any downstream pick that is no longer one of its slot's two
    (pick-derived) teams, cascading forward. Returns list of cleared match_ids.
    Caller commits."""
    matches_by_id = get_bracket_matches(db)
    picks = _user_bracket_picks(db, user_id)
    cleared = []
    for rk in ["R16", "QF", "SF", "FINAL"]:
        slot_teams = _compute_slot_teams(matches_by_id, picks)
        for mid in ROUNDS[rk]:
            p = picks.get(mid)
            if p is not None and p not in slot_teams[mid]:
                db.execute("DELETE FROM bracket_picks WHERE user_id=%s AND match_id=%s",
                           (user_id, mid))
                picks.pop(mid, None)
                cleared.append(mid)
    return cleared


def _bracket_render_payload(db, user_id):
    matches_by_id = get_bracket_matches(db)
    picks = _user_bracket_picks(db, user_id)
    slot_teams = _compute_slot_teams(matches_by_id, picks)
    acts = actual_sets(db)

    rounds = []
    for rk in ROUND_ORDER:
        score_round = {"R32": "R16", "R16": "QF", "QF": "SF",
                       "SF": "FINAL", "FINAL": "CHAMPION"}[rk]
        actual_for_round = acts.get(score_round)
        if score_round == "CHAMPION":
            actual_set = {actual_for_round} if actual_for_round else set()
        else:
            actual_set = actual_for_round or set()
        ms = []
        for mid in ROUNDS[rk]:
            picked = picks.get(mid)
            result_known = bool(actual_set)
            ms.append({
                "match_id": mid,
                "home": slot_teams[mid][0],
                "away": slot_teams[mid][1],
                "picked": picked,
                "result_known": result_known,
                "correct": (result_known and picked in actual_set) if picked else None,
            })
        picked_n = sum(1 for mid in ROUNDS[rk] if picks.get(mid))
        rounds.append({"key": rk, "label": ROUND_LABELS[rk], "matches": ms,
                       "picked_n": picked_n, "total_n": len(ROUNDS[rk])})
    return rounds, picks, slot_teams


@app.route("/bracket")
@login_required
def bracket():
    db = get_request_db()
    state = get_state(db)
    status = effective_status(state)

    if status == "coming_soon":
        return render_template("bracket_coming_soon.html", state=state)

    user_id = session["user_id"]
    rounds, picks, slot_teams = _bracket_render_payload(db, user_id)
    locked = (status == "locked")

    settlements = {s["round"]: s for s in db.execute(
        "SELECT * FROM bracket_settlements WHERE user_id=%s", (user_id,)
    ).fetchall()}
    total_pts = sum(s["total_points"] for s in settlements.values())

    # Maps for the client-side cascade.
    next_map = {str(mid): list(NEXT_SLOT[mid]) for mid in NEXT_SLOT}
    rounds_map = {rk: ROUNDS[rk] for rk in ROUND_ORDER}

    return render_template("bracket.html",
                           rounds=rounds, locked=locked, status=status,
                           picks={str(k): v for k, v in picks.items()},
                           slot_teams={str(k): v for k, v in slot_teams.items()},
                           feeds={str(k): list(v) for k, v in FEEDS.items()},
                           next_map=next_map, rounds_map=rounds_map,
                           settlements=settlements, total_pts=total_pts,
                           round_labels=ROUND_LABELS,
                           bracket_points=BRACKET_POINTS,
                           grand_max=grand_total_max())


@app.route("/api/bracket/pick", methods=["POST"])
@login_required
def api_bracket_pick():
    db = get_request_db()
    if not is_open_for_writes(db):
        return jsonify({"error": "Bracket is locked."}), 403

    data = request.get_json() or {}
    match_id = data.get("match_id")
    picked = (data.get("picked_team") or "").strip()

    try:
        match_id = int(match_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Bad match id."}), 400

    matches_by_id = get_bracket_matches(db)
    user_id = session["user_id"]
    picks = _user_bracket_picks(db, user_id)
    slot_teams = _compute_slot_teams(matches_by_id, picks)

    if match_id not in slot_teams:
        return jsonify({"error": "No such match."}), 404
    if not picked or picked not in slot_teams[match_id]:
        return jsonify({"error": "Pick must be one of the two teams in this matchup."}), 400

    now = datetime.now(timezone.utc).isoformat()
    db.execute("""
        INSERT INTO bracket_picks (user_id, match_id, picked_team, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT(user_id, match_id) DO UPDATE SET
            picked_team=EXCLUDED.picked_team, updated_at=EXCLUDED.updated_at
    """, (user_id, match_id, picked, now))

    cleared = _revalidate_picks(db, user_id)
    db.commit()

    new_picks = _user_bracket_picks(db, user_id)
    new_slots = _compute_slot_teams(matches_by_id, new_picks)
    progress = {rk: sum(1 for mid in ROUNDS[rk] if new_picks.get(mid))
                for rk in ROUND_ORDER}
    return jsonify({
        "ok": True,
        "cleared": cleared,
        "picks": {str(k): v for k, v in new_picks.items()},
        "slot_teams": {str(k): v for k, v in new_slots.items()},
        "progress": progress,
    })


@app.route("/bracket/leaderboard")
@login_required
def bracket_leaderboard():
    db = get_request_db()
    user_id = session["user_id"]
    state = get_state(db)
    if effective_status(state) == "coming_soon":
        return render_template("bracket_coming_soon.html", state=state)

    user_groups = db.execute("""
        SELECT g.* FROM groups g
        JOIN group_members gm ON gm.group_id=g.id
        WHERE gm.user_id=%s ORDER BY g.name
    """, (user_id,)).fetchall()

    selected_group = request.args.get("group", "everyone")

    # Tiebreakers: total points, then champion-correct, then earliest "locked"
    # (= earliest last-edit time across the user's picks → committed soonest).
    def standings(group_id=None):
        where = ""
        params = []
        if group_id:
            where = "JOIN group_members gm ON gm.user_id=u.id AND gm.group_id=%s"
            params.append(group_id)
        sql = f"""
            SELECT u.id, u.team_name,
                COALESCE(SUM(bs.total_points), 0) AS total_points,
                COALESCE(MAX(CASE WHEN bs.round='CHAMPION' THEN bs.correct_count END), 0)
                    AS champion_correct,
                (SELECT MAX(bp.updated_at) FROM bracket_picks bp WHERE bp.user_id=u.id)
                    AS last_edit,
                (SELECT COUNT(*) FROM bracket_picks bp WHERE bp.user_id=u.id)
                    AS picks_made
            FROM users u
            {where}
            LEFT JOIN bracket_settlements bs ON bs.user_id=u.id
            GROUP BY u.id, u.team_name
            HAVING (SELECT COUNT(*) FROM bracket_picks bp WHERE bp.user_id=u.id) > 0
            ORDER BY total_points DESC, champion_correct DESC, last_edit ASC
        """
        return db.execute(sql, params).fetchall()

    selected_group_obj = None
    if selected_group == "everyone":
        rows = standings()
    else:
        try:
            gid = int(selected_group)
            rows = standings(gid)
            selected_group_obj = next((g for g in user_groups if g["id"] == gid), None)
        except ValueError:
            rows = standings()

    return render_template("bracket_leaderboard.html",
                           user_groups=user_groups, standings=rows,
                           selected_group=selected_group,
                           selected_group_obj=selected_group_obj,
                           current_user_id=user_id, grand_max=grand_total_max())


# ── Admin: confirm & open the bracket (gated by ADMIN_KEY) ────────────────────

def _check_admin():
    if not ADMIN_KEY:
        return False
    key = request.values.get("key", "")
    return key == ADMIN_KEY


@app.route("/admin/bracket", methods=["GET", "POST"])
def admin_bracket():
    if not _check_admin():
        return ("Forbidden — append ?key=ADMIN_KEY (and set ADMIN_KEY in .env).", 403)

    db = get_request_db()
    state = get_state(db)
    msg = None

    if request.method == "POST":
        action = request.form.get("action")
        if action == "edit":
            mid = int(request.form["match_id"])
            home = (request.form.get("home_team") or "").strip() or None
            away = (request.form.get("away_team") or "").strip() or None
            db.execute(
                "UPDATE bracket_matches SET home_team=%s, away_team=%s WHERE match_id=%s",
                (home, away, mid))
            db.commit()
            msg = f"Updated matchup {mid}."
        elif action == "confirm":
            r32 = db.execute(
                "SELECT match_id, home_team, away_team FROM bracket_matches "
                "WHERE round='R32'").fetchall()
            missing = [r["match_id"] for r in r32
                       if not r["home_team"] or not r["away_team"]]
            if len(r32) != 16 or missing:
                msg = (f"Cannot open: {len(r32)}/16 R32 slots present, "
                       f"missing teams in {missing}. Fill all R32 matchups first.")
            else:
                now = datetime.now(timezone.utc).isoformat()
                db.execute(
                    "UPDATE bracket_state SET status='open', open_at=%s, confirmed_at=%s "
                    "WHERE id=1", (now, now))
                db.commit()
                msg = "✅ Bracket is now OPEN. Users can fill their brackets."
        elif action == "set_lock":
            lock_at = (request.form.get("lock_at") or "").strip() or None
            db.execute("UPDATE bracket_state SET lock_at=%s WHERE id=1", (lock_at,))
            db.commit()
            msg = f"Lock time set to {lock_at}."
        state = get_state(db)

    matches = db.execute(
        "SELECT * FROM bracket_matches ORDER BY round, match_id").fetchall()
    by_round = {}
    for m in matches:
        by_round.setdefault(m["round"], []).append(m)
    status = effective_status(state)

    return render_template("admin_bracket.html",
                           state=state, status=status, by_round=by_round,
                           round_order=ROUND_ORDER, round_labels=ROUND_LABELS,
                           key=request.values.get("key", ""), msg=msg)


# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
