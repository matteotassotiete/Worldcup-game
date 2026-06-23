CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    team_name TEXT UNIQUE NOT NULL,
    pin_hash TEXT NOT NULL,
    champion_pick TEXT,
    top_scorer_pick TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id INTEGER NOT NULL REFERENCES groups(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    UNIQUE(group_id, user_id)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    match_id INTEGER NOT NULL REFERENCES matches(id),
    home_pred INTEGER NOT NULL,
    away_pred INTEGER NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, match_id)
);

CREATE TABLE IF NOT EXISTS tournament_awards (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    champion_points INTEGER NOT NULL DEFAULT 0,
    top_scorer_points INTEGER NOT NULL DEFAULT 0,
    awarded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS settlements (
    id SERIAL PRIMARY KEY,
    prediction_id INTEGER UNIQUE NOT NULL REFERENCES predictions(id),
    base_points INTEGER NOT NULL,
    bonus_points INTEGER NOT NULL,
    bonus_labels TEXT NOT NULL DEFAULT '',
    total_points INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Bracket Game (independent of the score game above) ───────────────────────

-- The actual tournament bracket. match_id is the hardcoded skeleton slot id
-- (73..104), NOT the football-data.org id. home_advances: 1 = home team went
-- through, 0 = away team went through, NULL = not decided yet.
CREATE TABLE IF NOT EXISTS bracket_matches (
    match_id INTEGER PRIMARY KEY,
    round TEXT NOT NULL,
    home_team TEXT,
    away_team TEXT,
    home_advances INTEGER,
    api_match_id INTEGER,
    status TEXT NOT NULL DEFAULT 'SCHEDULED',
    settled INTEGER NOT NULL DEFAULT 0
);

-- Single-row game state machine.
CREATE TABLE IF NOT EXISTS bracket_state (
    id INTEGER PRIMARY KEY CHECK(id=1),
    status TEXT NOT NULL DEFAULT 'coming_soon',  -- 'coming_soon'|'open'|'locked'
    open_at TEXT,
    lock_at TEXT,
    confirmed_at TEXT
);

CREATE TABLE IF NOT EXISTS bracket_picks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    match_id INTEGER NOT NULL REFERENCES bracket_matches(match_id),
    picked_team TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, match_id)
);

CREATE TABLE IF NOT EXISTS bracket_settlements (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    round TEXT NOT NULL,
    correct_count INTEGER NOT NULL,
    base_points INTEGER NOT NULL,
    bonus_points INTEGER NOT NULL,
    total_points INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, round)
);
