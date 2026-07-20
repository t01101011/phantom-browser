-- Task 8: persist stop idempotency independently from start idempotency.
ALTER TABLE sessions ADD COLUMN stop_idempotency_key TEXT;
CREATE UNIQUE INDEX idx_sessions_stop_idempotency
    ON sessions(stop_idempotency_key)
    WHERE stop_idempotency_key IS NOT NULL;
CREATE INDEX idx_events_session_sequence ON events(session_id, sequence);
