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

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

# Tournament picks lock: June 11 2026 at 11:00 UTC (8h before first kickoff)
PICKS_LOCK_UTC = datetime(2026, 6, 11, 11, 0, 0, tzinfo=timezone.utc)


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
        return {"nav_groups": groups}
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
    return datetime.now(timezone.utc) < kickoff - timedelta(hours=1)


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
                    COUNT(p.id) AS predictions_made
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
                    COUNT(p.id) AS predictions_made
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


# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
