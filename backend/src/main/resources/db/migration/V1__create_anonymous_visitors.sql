CREATE TABLE IF NOT EXISTS anonymous_visitors (
    visitor_id UUID PRIMARY KEY,
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
    trial_used_at TIMESTAMP WITH TIME ZONE NULL,
    trial_run_id UUID NULL,
    ip_hash VARCHAR(255) NULL,
    blocked_reason VARCHAR(255) NULL
);
