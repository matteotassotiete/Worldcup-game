CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT UNIQUE COLLATE NOCASE NOT NULL,
    pin_hash TEXT NOT NULL,
    champion_pick TEXT,
    top_scorer_pick TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    UNIQUE(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,   -- football-data.org match id
    kickoff_utc TEXT NOT NULL,
    stage TEXT NOT NULL,
    group_label TEXT,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    status TEXT NOT NULL DEFAULT 'SCHEDULED',
    settled INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    match_id INTEGER NOT NULL REFERENCES matches(id),
    home_pred INTEGER NOT NULL,
    away_pred INTEGER NOT NULL,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, match_id)
);

CREATE TABLE IF NOT EXISTS tournament_awards (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    champion_points INTEGER NOT NULL DEFAULT 0,
    top_scorer_points INTEGER NOT NULL DEFAULT 0,
    awarded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id INTEGER UNIQUE NOT NULL REFERENCES predictions(id),
    base_points INTEGER NOT NULL,
    bonus_points INTEGER NOT NULL,
    bonus_labels TEXT NOT NULL DEFAULT '',
    total_points INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
