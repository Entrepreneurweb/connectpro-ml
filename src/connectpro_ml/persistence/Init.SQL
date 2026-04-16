CREATE TABLE IF NOT EXISTS items (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    category   VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);