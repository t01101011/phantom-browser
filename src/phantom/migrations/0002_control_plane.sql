-- Phantom Browser control-plane schema v2.
-- This migration is additive: legacy profiles/running_instances remain usable.

CREATE TABLE folders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    parent_id       INTEGER REFERENCES folders(id) ON DELETE SET NULL,
    defaults_json   TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE proxies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    scheme          TEXT NOT NULL DEFAULT 'http',
    host            TEXT NOT NULL,
    port            INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
    username        TEXT NOT NULL DEFAULT '',
    password        TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT 'manual',
    health_status   TEXT NOT NULL DEFAULT 'unknown',
    last_checked_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (scheme, host, port, username)
);

ALTER TABLE profiles ADD COLUMN folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL;
ALTER TABLE profiles ADD COLUMN proxy_id INTEGER REFERENCES proxies(id) ON DELETE SET NULL;

CREATE TABLE sessions (
    id                TEXT PRIMARY KEY,
    profile_id        INTEGER REFERENCES profiles(id) ON DELETE SET NULL,
    mode              TEXT NOT NULL DEFAULT 'persistent'
                      CHECK (mode IN ('persistent', 'instant')),
    status            TEXT NOT NULL DEFAULT 'starting'
                      CHECK (status IN ('queued', 'starting', 'ready', 'stopping', 'stopped', 'crashed')),
    worker_pid        INTEGER,
    user_data_dir     TEXT NOT NULL,
    capability_json   TEXT NOT NULL DEFAULT '{}',
    idempotency_key   TEXT UNIQUE,
    exit_reason       TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    stopped_at        TEXT
);

CREATE TABLE session_leases (
    session_id        TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    owner_token_hash  TEXT NOT NULL,
    generation        INTEGER NOT NULL DEFAULT 1,
    lease_expires_at  TEXT NOT NULL,
    heartbeat_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sequence        INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (session_id, sequence)
);

CREATE TABLE artifacts (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    artifact_type   TEXT NOT NULL,
    path            TEXT NOT NULL,
    content_type    TEXT,
    size_bytes      INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    checksum_sha256 TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at      TEXT
);

CREATE INDEX idx_profiles_folder ON profiles(folder_id);
CREATE INDEX idx_profiles_proxy_id ON profiles(proxy_id);
CREATE INDEX idx_sessions_profile_status ON sessions(profile_id, status);
CREATE INDEX idx_sessions_status_created ON sessions(status, created_at);
CREATE INDEX idx_session_leases_expires ON session_leases(lease_expires_at);
CREATE INDEX idx_events_session_created ON events(session_id, created_at);
CREATE INDEX idx_artifacts_session_created ON artifacts(session_id, created_at);
