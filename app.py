import os
import random
import string
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash, g)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

from db import get_db, init_db

app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]

TOURNAMENT_LOCK_MATCH_ID = None  # set lazily from DB (first kickoff)


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
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()


def tournament_locked():
    db = get_db()
    first = db.execute(
        "SELECT kickoff_utc FROM matches ORDER BY kickoff_utc LIMIT 1"
    ).fetchone()
    if not first:
        return False
    lock_dt = datetime.fromisoformat(first["kickoff_utc"].replace("Z", "+00:00"))
    return datetime.now(timezone.utc) >= lock_dt


def generate_group_code():
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
    while True:
        code = "".join(random.choices(chars, k=6))
        db = get_db()
        existing = db.execute("SELECT id FROM groups WHERE code=?", (code,)).fetchone()
        if not existing:
            return code


def prediction_is_open(kickoff_utc_str):
    kickoff = datetime.fromisoformat(kickoff_utc_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return now < kickoff - __import__("datetime").timedelta(hours=1)


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
        db = get_db()
        try:
            cur = db.execute(
                "INSERT INTO users (team_name, pin_hash) VALUES (?, ?)",
                (team_name, pin_hash)
            )
            db.commit()
            session["user_id"] = cur.lastrowid
            session["team_name"] = team_name
            return redirect(url_for("group"))
        except Exception:
            flash("That team name is already taken.")
            return render_template("signup.html")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        team_name = request.form.get("team_name", "").strip()
        pin = request.form.get("pin", "").strip()

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE team_name=? COLLATE NOCASE", (team_name,)
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
        db = get_db()
        user_id = session["user_id"]

        if action == "create":
            name = request.form.get("group_name", "").strip()
            if not name:
                flash("Group name required.")
                return render_template("group.html")
            code = generate_group_code()
            cur = db.execute("INSERT INTO groups (name, code) VALUES (?, ?)", (name, code))
            group_id = cur.lastrowid
            db.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)", (group_id, user_id))
            db.commit()
            return render_template("group.html", created_code=code, created_name=name)

        elif action == "join":
            code = request.form.get("code", "").strip().upper()
            grp = db.execute("SELECT * FROM groups WHERE code=?", (code,)).fetchone()
            if not grp:
                flash("Group not found. Check the code.")
                return render_template("group.html")
            try:
                db.execute("INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
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
    db = get_db()
    user = get_current_user()

    if request.method == "POST":
        if locked:
            flash("Tournament has started — picks are locked.")
            return redirect(url_for("picks"))
        champion = request.form.get("champion_pick", "").strip()
        top_scorer = request.form.get("top_scorer_pick", "").strip()
        db.execute(
            "UPDATE users SET champion_pick=?, top_scorer_pick=? WHERE id=?",
            (champion or None, top_scorer or None, session["user_id"])
        )
        db.commit()
        flash("Picks saved!")
        return redirect(url_for("picks"))

    # Build team list from matches
    teams = set()
    for row in db.execute("SELECT home_team, away_team FROM matches"):
        teams.add(row["home_team"])
        teams.add(row["away_team"])
    teams = sorted(teams)

    return render_template("picks.html", user=user, teams=teams, locked=locked)


@app.route("/predict")
@login_required
def predict():
    db = get_db()
    user_id = session["user_id"]

    matches = db.execute(
        "SELECT * FROM matches ORDER BY kickoff_utc"
    ).fetchall()

    # Fetch user's predictions keyed by match_id
    preds = {row["match_id"]: row for row in db.execute(
        "SELECT * FROM predictions WHERE user_id=?", (user_id,)
    )}

    # Fetch settlements for user's predictions
    settled_map = {}
    if preds:
        pred_ids = list(preds.keys())
        placeholders = ",".join("?" * len(pred_ids))
        for row in db.execute(
            f"SELECT s.*, p.match_id FROM settlements s "
            f"JOIN predictions p ON p.id=s.prediction_id "
            f"WHERE p.user_id=? AND p.match_id IN ({placeholders})",
            [user_id] + pred_ids
        ):
            settled_map[row["match_id"]] = row

    now_utc = datetime.now(timezone.utc).isoformat()
    open_map = {m["id"]: prediction_is_open(m["kickoff_utc"]) for m in matches}
    return render_template("predict.html",
                           matches=matches,
                           preds=preds,
                           settled_map=settled_map,
                           open_map=open_map,
                           now_utc=now_utc)


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

    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if not match:
        return jsonify({"error": "Match not found."}), 404

    if not prediction_is_open(match["kickoff_utc"]):
        return jsonify({"error": "Predictions are locked for this match."}), 403

    user_id = session["user_id"]
    db.execute("""
        INSERT INTO predictions (user_id, match_id, home_pred, away_pred, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(user_id, match_id) DO UPDATE SET
            home_pred=excluded.home_pred,
            away_pred=excluded.away_pred,
            updated_at=excluded.updated_at
    """, (user_id, match_id, home_pred, away_pred))
    db.commit()
    return jsonify({"ok": True})


@app.route("/leaderboard")
@login_required
def leaderboard():
    db = get_db()
    user_id = session["user_id"]

    # Groups the user belongs to
    user_groups = db.execute("""
        SELECT g.* FROM groups g
        JOIN group_members gm ON gm.group_id=g.id
        WHERE gm.user_id=?
        ORDER BY g.name
    """, (user_id,)).fetchall()

    selected_group = request.args.get("group", "everyone")

    def get_standings(group_id=None):
        if group_id:
            rows = db.execute("""
                SELECT u.id, u.team_name,
                    COALESCE(SUM(s.total_points), 0)
                    + COALESCE(ta.champion_points, 0)
                    + COALESCE(ta.top_scorer_points, 0) AS total_points,
                    COUNT(CASE WHEN s.base_points=100 THEN 1 END) AS exacts,
                    COUNT(p.id) AS predictions_made
                FROM users u
                JOIN group_members gm ON gm.user_id=u.id AND gm.group_id=?
                LEFT JOIN predictions p ON p.user_id=u.id
                LEFT JOIN settlements s ON s.prediction_id=p.id
                LEFT JOIN tournament_awards ta ON ta.user_id=u.id
                GROUP BY u.id
                ORDER BY total_points DESC, exacts DESC
            """, (group_id,)).fetchall()
        else:
            rows = db.execute("""
                SELECT u.id, u.team_name,
                    COALESCE(SUM(s.total_points), 0)
                    + COALESCE(ta.champion_points, 0)
                    + COALESCE(ta.top_scorer_points, 0) AS total_points,
                    COUNT(CASE WHEN s.base_points=100 THEN 1 END) AS exacts,
                    COUNT(p.id) AS predictions_made
                FROM users u
                LEFT JOIN predictions p ON p.user_id=u.id
                LEFT JOIN settlements s ON s.prediction_id=p.id
                LEFT JOIN tournament_awards ta ON ta.user_id=u.id
                GROUP BY u.id
                ORDER BY total_points DESC, exacts DESC
            """).fetchall()
        return rows

    if selected_group == "everyone":
        standings = get_standings()
    else:
        try:
            gid = int(selected_group)
            standings = get_standings(gid)
        except ValueError:
            standings = get_standings()

    return render_template("leaderboard.html",
                           user_groups=user_groups,
                           standings=standings,
                           selected_group=selected_group,
                           current_user_id=user_id)


# ── Init ──────────────────────────────────────────────────────────────────────

with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
