CREATE TABLE pending_interactions (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID NOT NULL,
    item_type           TEXT NOT NULL,
    item_id             UUID NOT NULL,
    interaction_type    TEXT NOT NULL,
    weight              NUMERIC NOT NULL,
    source              TEXT,
    position            INTEGER,
    occurred_at         TIMESTAMPTZ NOT NULL,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_profiles (
    user_id                 UUID PRIMARY KEY,
    semantic_embedding      BYTEA NOT NULL,
    total_interactions_used INTEGER NOT NULL DEFAULT 0,
    embedding_version       TEXT NOT NULL,
    last_computed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE portfolios (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL,
    type            TEXT NOT NULL,
    status          TEXT NOT NULL,
    first_name      TEXT,
    last_name       TEXT,
    bio             TEXT,
    country         TEXT,
    city            TEXT,
    timezone        TEXT,
    headline        TEXT,
    active_services_count   INTEGER NOT NULL DEFAULT 0,
    profile_embedding       BYTEA,
    embedding_version       TEXT,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_portfolios_owner UNIQUE (owner_id)
);

CREATE TABLE portfolio_skills (
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    skill           TEXT NOT NULL,
    PRIMARY KEY (portfolio_id, skill)
);

CREATE TABLE portfolio_experiences (
    id              UUID PRIMARY KEY,
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    company         TEXT NOT NULL,
    role            TEXT NOT NULL,
    description     TEXT,
    start_date      DATE NOT NULL,
    end_date        DATE
);

CREATE TABLE portfolio_certifications (
    id                      UUID PRIMARY KEY,
    portfolio_id            UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    name                    TEXT NOT NULL,
    issuing_organization    TEXT NOT NULL,
    issue_date              DATE NOT NULL,
    expiry_date             DATE,
    credential_url          TEXT
);

CREATE TABLE categories (
    id      UUID PRIMARY KEY,
    value   TEXT NOT NULL UNIQUE
);

CREATE TABLE services (
    id              UUID PRIMARY KEY,
    portfolio_id    UUID,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL,
    category_id     UUID,
    pricing_type    TEXT,
    price_min       NUMERIC,
    price_max       NUMERIC,
    currency        TEXT,
    embedding       BYTEA,
    embedding_version TEXT,
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE service_tags (
    service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    tag_id      UUID NOT NULL,
    value       TEXT NOT NULL,
    PRIMARY KEY (service_id, tag_id)
);

CREATE TABLE service_awards (
    service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    award_id    UUID NOT NULL,
    value       TEXT NOT NULL,
    PRIMARY KEY (service_id, award_id)
);

CREATE TABLE service_faqs (
    id          UUID PRIMARY KEY,
    service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL
);

CREATE TABLE job_posts (
    id              UUID PRIMARY KEY,
    client_id       UUID NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL,
    budget_type     TEXT,
    budget_min      NUMERIC,
    budget_max      NUMERIC,
    currency        TEXT,
    embedding       BYTEA,
    embedding_version TEXT,
    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE reviews (
    id              UUID PRIMARY KEY,
    service_id      UUID NOT NULL,
    reviewer_id     UUID NOT NULL,
    rating          NUMERIC NOT NULL,
    comment         TEXT,
    status          TEXT NOT NULL,
    created_at      TIMESTAMPTZ
);

CREATE TABLE interactions (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID NOT NULL,
    item_type           TEXT NOT NULL,
    item_id             UUID NOT NULL,
    interaction_type    TEXT NOT NULL,
    weight              NUMERIC NOT NULL,
    source              TEXT,
    position            INTEGER,
    occurred_at         TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_interaction UNIQUE (user_id, item_id, interaction_type)
);

CREATE TABLE follows (
    user_id         UUID NOT NULL,
    portfolio_id    UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, portfolio_id)
);

CREATE TABLE dismissed_items (
    user_id     UUID NOT NULL,
    item_id     UUID NOT NULL,
    item_type   TEXT NOT NULL,
    dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, item_id)
);

CREATE TABLE user_category_affinity (
    user_id         UUID NOT NULL,
    category_id     UUID NOT NULL,
    score           NUMERIC NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, category_id)
);

CREATE TABLE user_tag_affinity (
    user_id         UUID NOT NULL,
    tag_value       TEXT NOT NULL,
    score           NUMERIC NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, tag_value)
);

CREATE TABLE user_skill_affinity (
    user_id         UUID NOT NULL,
    skill           TEXT NOT NULL,
    score           NUMERIC NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, skill)
);

CREATE TABLE feed_impressions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL,
    item_id     UUID NOT NULL,
    item_type   TEXT NOT NULL,
    position    INTEGER NOT NULL,
    score       NUMERIC,
    served_at   TIMESTAMPTZ NOT NULL
);

CREATE TABLE recompute_log (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL,
    reason          TEXT NOT NULL,
    algo_version    TEXT NOT NULL,
    item_count      INTEGER NOT NULL,
    duration_ms     INTEGER NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE MATERIALIZED VIEW service_review_stats AS
SELECT
    service_id,
    COUNT(*) AS review_count,
    AVG(rating) AS avg_rating
FROM reviews
WHERE status = 'published'
GROUP BY service_id;

CREATE UNIQUE INDEX ON service_review_stats(service_id);

CREATE MATERIALIZED VIEW portfolio_review_stats AS
SELECT
    p.id AS portfolio_id,
    COUNT(r.id) AS total_review_count,
    AVG(r.rating) AS avg_rating
FROM portfolios p
JOIN services s ON s.portfolio_id = p.id
JOIN reviews r ON r.service_id = s.id
WHERE r.status = 'published'
GROUP BY p.id;

CREATE UNIQUE INDEX ON portfolio_review_stats(portfolio_id);

-- CREATE TABLE pending_interactions (
--     id                  BIGSERIAL PRIMARY KEY,
--     user_id             UUID NOT NULL,
--     item_type           TEXT NOT NULL,
--     item_id             UUID NOT NULL,
--     interaction_type    TEXT NOT NULL,
--     weight              NUMERIC NOT NULL,
--     source              TEXT,
--     position            INTEGER,
--     occurred_at         TIMESTAMPTZ NOT NULL,
--     received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
--
-- -- CREATE INDEX idx_pending_user ON pending_interactions (user_id);
-- -- CREATE INDEX idx_pending_received ON pending_interactions (received_at);
--
-- CREATE TABLE user_profiles (
--     user_id                 UUID PRIMARY KEY,
--     semantic_embedding      BYTEA NOT NULL,
--     total_interactions_used INTEGER NOT NULL DEFAULT 0,
--     embedding_version       TEXT NOT NULL,
--     last_computed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
--
-- CREATE TABLE portfolios (
--     id              UUID PRIMARY KEY,
--     owner_id        UUID NOT NULL,
--     type            TEXT NOT NULL,
--     status          TEXT NOT NULL,
--
--     -- GeneralInfo
--     first_name      TEXT,
--     last_name       TEXT,
--     bio             TEXT,
--
--     -- LocationInfo
--     country         TEXT,
--     city            TEXT,
--     timezone        TEXT,
--
--     -- ProfessionalInfo
--     headline        TEXT,
--
-- --     -- ContactInfo
-- --     website_url     TEXT,
--
--
--     active_services_count   INTEGER NOT NULL DEFAULT 0,
--
--     -- Embedding & reco
--     profile_embedding       BYTEA,
--     embedding_version       TEXT,
--
--     synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--
--     CONSTRAINT uq_portfolios_owner UNIQUE (owner_id)
-- );
--
-- -- CREATE INDEX idx_portfolios_status ON portfolios (status) WHERE status = 'active';
--
--
-- -- ----------------------------------------------------------------------------
-- --  PORTFOLIO — SKILLS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE portfolio_skills (
--     portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
--     skill           TEXT NOT NULL,
--     PRIMARY KEY (portfolio_id, skill)
-- );
--
-- -- CREATE INDEX idx_portfolio_skills_skill ON portfolio_skills (skill);
--
--
-- -- ----------------------------------------------------------------------------
-- --  PORTFOLIO — EXPERIENCES
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE portfolio_experiences (
--     id              UUID PRIMARY KEY,
--     portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
--     company         TEXT NOT NULL,
--     role            TEXT NOT NULL,
--     description     TEXT,
--     start_date      DATE NOT NULL,
--     end_date        DATE
-- );
--
-- -- CREATE INDEX idx_experiences_portfolio ON portfolio_experiences (portfolio_id);
--
--
-- -- ----------------------------------------------------------------------------
-- -- PORTFOLIO — CERTIFICATIONS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE portfolio_certifications (
--     id                      UUID PRIMARY KEY,
--     portfolio_id            UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
--     name                    TEXT NOT NULL,
--     issuing_organization    TEXT NOT NULL,
--     issue_date              DATE NOT NULL,
--     expiry_date             DATE,
--     credential_url          TEXT
-- );
--
-- -- CREATE INDEX idx_certifications_portfolio ON portfolio_certifications (portfolio_id);
--
--
-- -- ----------------------------------------------------------------------------
-- --  CATEGORIES
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE categories (
--     id      UUID PRIMARY KEY,
--     value   TEXT NOT NULL UNIQUE
-- );
--
--
-- -- ----------------------------------------------------------------------------
-- --  SERVICES
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE services (
--     id              UUID PRIMARY KEY,
--     portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
--     title           TEXT NOT NULL,
--     description     TEXT NOT NULL,
--     status          TEXT NOT NULL,
--     category_id     UUID REFERENCES categories(id),
--
--     -- Pricing
--     pricing_type    TEXT,
--     price_min       NUMERIC,
--     price_max       NUMERIC,
--     currency        TEXT,
--
--     -- Embedding & reco
--     embedding       BYTEA,
--     embedding_version TEXT,
--
--     created_at      TIMESTAMPTZ,
--     updated_at      TIMESTAMPTZ,
--     synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
--
-- -- CREATE INDEX idx_services_portfolio ON services (portfolio_id);
-- -- CREATE INDEX idx_services_category ON services (category_id);
-- -- CREATE INDEX idx_services_active ON services (status) WHERE status = 'active';
--
--
-- -- ----------------------------------------------------------------------------
-- --  SERVICE — TAGS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE service_tags (
--     service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
--     tag_id      UUID NOT NULL,
--     value       TEXT NOT NULL,
--     PRIMARY KEY (service_id, tag_id)
-- );
--
-- -- CREATE INDEX idx_service_tags_value ON service_tags (value);
--
--
-- -- ----------------------------------------------------------------------------
-- --  SERVICE — AWARDS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE service_awards (
--     service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
--     award_id    UUID NOT NULL,
--     value       TEXT NOT NULL,
--     PRIMARY KEY (service_id, award_id)
-- );
--
--
-- -- ----------------------------------------------------------------------------
-- --  SERVICE — FAQS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE service_faqs (
--     id          UUID PRIMARY KEY,
--     service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
--     question    TEXT NOT NULL,
--     answer      TEXT NOT NULL
-- );
--
-- -- CREATE INDEX idx_faqs_service ON service_faqs (service_id);
--
--
-- -- ----------------------------------------------------------------------------
-- --  JOB POSTS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE job_posts (
--     id              UUID PRIMARY KEY,
--     client_id       UUID NOT NULL,
--     title           TEXT NOT NULL,
--     description     TEXT NOT NULL,
--     status          TEXT NOT NULL,
--
--     -- Budget
--     budget_type     TEXT,
--     budget_min      NUMERIC,
--     budget_max      NUMERIC,
--     currency        TEXT,
--
--     -- Embedding & reco
--     embedding       BYTEA,
--     embedding_version TEXT,
--
--     created_at      TIMESTAMPTZ,
--     updated_at      TIMESTAMPTZ,
--     synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
--
-- -- CREATE INDEX idx_job_posts_client ON job_posts (client_id);
-- -- CREATE INDEX idx_job_posts_open ON job_posts (status) WHERE status = 'open';
--
--
-- -- ----------------------------------------------------------------------------
-- --   REVIEWS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE reviews (
--     id              UUID PRIMARY KEY,
--     service_id      UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
--     reviewer_id     UUID NOT NULL,
--     rating          NUMERIC NOT NULL,
--     comment         TEXT,
--     status          TEXT NOT NULL,
--     created_at      TIMESTAMPTZ
-- );
--
-- -- CREATE INDEX idx_reviews_service ON reviews (service_id) WHERE status = 'published';
--
--
-- CREATE MATERIALIZED VIEW service_review_stats AS
-- SELECT
--     service_id,
--     COUNT(*)            AS review_count,
--     AVG(rating)         AS avg_rating,
--     MIN(rating)         AS min_rating,
--     MAX(rating)         AS max_rating
-- FROM reviews
-- WHERE status = 'published'
-- GROUP BY service_id;
--
-- -- CREATE UNIQUE INDEX idx_review_stats_service ON service_review_stats (service_id);
--
-- CREATE MATERIALIZED VIEW portfolio_review_stats AS
-- SELECT
--     s.portfolio_id,
--     COUNT(r.id)         AS total_review_count,
--     AVG(r.rating)       AS avg_rating
-- FROM reviews r
-- JOIN services s ON s.id = r.service_id
-- WHERE r.status = 'published'
-- GROUP BY s.portfolio_id;
-- --
-- -- CREATE UNIQUE INDEX idx_portfolio_review_stats ON portfolio_review_stats (portfolio_id);
--
--
-- -- ============================================================================
-- --  TABLES PROPRES AU RECO
-- -- ============================================================================
--
-- -- ----------------------------------------------------------------------------
-- -- INTERACTIONS UTILISATEUR
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE interactions (
--     id                  BIGSERIAL PRIMARY KEY,
--     user_id             UUID NOT NULL,
--     item_type           TEXT NOT NULL,
--     item_id             UUID NOT NULL,
--     interaction_type    TEXT NOT NULL,
--     weight              NUMERIC NOT NULL,
--     source              TEXT,
--     position            INTEGER,
--     occurred_at         TIMESTAMPTZ NOT NULL,
--
--     CONSTRAINT uq_interaction UNIQUE (user_id, item_id, interaction_type)
-- );
-- --
-- -- CREATE INDEX idx_interactions_user_recent ON interactions (user_id, occurred_at DESC);
-- -- CREATE INDEX idx_interactions_item ON interactions (item_id);
--
--
-- -- ----------------------------------------------------------------------------
-- -- FOLLOWS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE follows (
--     user_id         UUID NOT NULL,
--     portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
--     created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     PRIMARY KEY (user_id, portfolio_id)
-- );
--
-- -- CREATE INDEX idx_follows_portfolio ON follows (portfolio_id);
--
--
-- -- ----------------------------------------------------------------------------
-- --  ITEMS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE dismissed_items (
--     user_id     UUID NOT NULL,
--     item_id     UUID NOT NULL,
--     item_type   TEXT NOT NULL,
--     dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     PRIMARY KEY (user_id, item_id)
-- );
--
--
-- -- ----------------------------------------------------------------------------
-- -- AFFINITÉS UTILISATEUR — CATÉGORIES
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE user_category_affinity (
--     user_id         UUID NOT NULL,
--     category_id     UUID NOT NULL REFERENCES categories(id),
--     score           NUMERIC NOT NULL DEFAULT 0,
--     interaction_count INTEGER NOT NULL DEFAULT 0,
--     last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     PRIMARY KEY (user_id, category_id)
-- );
--
--
-- -- ----------------------------------------------------------------------------
-- -- AFFINITÉS UTILISATEUR — TAGS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE user_tag_affinity (
--     user_id         UUID NOT NULL,
--     tag_value       TEXT NOT NULL,
--     score           NUMERIC NOT NULL DEFAULT 0,
--     interaction_count INTEGER NOT NULL DEFAULT 0,
--     last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     PRIMARY KEY (user_id, tag_value)
-- );
--
--
-- -- ----------------------------------------------------------------------------
-- -- AFFINITÉS UTILISATEUR — SKILLS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE user_skill_affinity (
--     user_id         UUID NOT NULL,
--     skill           TEXT NOT NULL,
--     score           NUMERIC NOT NULL DEFAULT 0,
--     interaction_count INTEGER NOT NULL DEFAULT 0,
--     last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     PRIMARY KEY (user_id, skill)
-- );
--
--
-- -- ----------------------------------------------------------------------------
-- -- FEED IMPRESSIONS
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE feed_impressions (
--     id          BIGSERIAL PRIMARY KEY,
--     user_id     UUID NOT NULL,
--     item_id     UUID NOT NULL,
--     item_type   TEXT NOT NULL,
--     position    INTEGER NOT NULL,
--     score       NUMERIC,
--     served_at   TIMESTAMPTZ NOT NULL
-- );
--
-- -- CREATE INDEX idx_impressions_user_time ON feed_impressions (user_id, served_at DESC);
--
--
--
-- -- ----------------------------------------------------------------------------
-- --  RECOMPUTE LOG
-- -- ----------------------------------------------------------------------------
--
-- CREATE TABLE recompute_log (
--     id              BIGSERIAL PRIMARY KEY,
--     user_id         UUID NOT NULL,
--     reason          TEXT NOT NULL,
--     algo_version    TEXT NOT NULL,
--     item_count      INTEGER NOT NULL,
--     duration_ms     INTEGER NOT NULL,
--     computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
--
-- -- CREATE INDEX idx_recompute_log_user ON recompute_log (user_id, computed_at DESC);
--
