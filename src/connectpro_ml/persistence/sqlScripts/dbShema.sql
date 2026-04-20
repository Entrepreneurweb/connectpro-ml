-- ============================================================================
-- RECOMMENDATION MICROSERVICE — POSTGRESQL SCHEMA
-- Base de données locale du microservice Python de recommandation.
-- Miroir partiel des entités .NET, alimenté par events RabbitMQ.
-- ============================================================================

-- ============================================================================
-- 1. TABLES MIROIR (synchronisées depuis .NET via events)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1.1 PORTFOLIOS (freelancers)
-- ----------------------------------------------------------------------------

CREATE TABLE portfolios (
    id              UUID PRIMARY KEY,
    owner_id        UUID NOT NULL,
    type            TEXT NOT NULL,               -- 'freelancer' | 'agency' | ...
    status          TEXT NOT NULL,               -- 'active' | 'inactive' | 'suspended'

    -- GeneralInfo (aplati)
    first_name      TEXT,
    last_name       TEXT,
    bio             TEXT,

    -- LocationInfo (aplati)
    country         TEXT,
    city            TEXT,
    timezone        TEXT,

    -- ProfessionalInfo (aplati)
    headline        TEXT,

    -- ContactInfo (aplati — seulement ce qui sert au reco/matching)
    website_url     TEXT,

    -- Compteurs & métriques agrégées
    active_services_count   INTEGER NOT NULL DEFAULT 0,

    -- Embedding & reco
    profile_embedding       BYTEA,              -- embedding calculé depuis bio + headline + skills + experiences
    embedding_version       TEXT,

    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_portfolios_owner UNIQUE (owner_id)
);

CREATE INDEX idx_portfolios_status ON portfolios (status) WHERE status = 'active';


-- ----------------------------------------------------------------------------
-- 1.2 PORTFOLIO — SKILLS
-- ----------------------------------------------------------------------------

CREATE TABLE portfolio_skills (
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    skill           TEXT NOT NULL,
    PRIMARY KEY (portfolio_id, skill)
);

CREATE INDEX idx_portfolio_skills_skill ON portfolio_skills (skill);


-- ----------------------------------------------------------------------------
-- 1.3 PORTFOLIO — EXPERIENCES
-- ----------------------------------------------------------------------------

CREATE TABLE portfolio_experiences (
    id              UUID PRIMARY KEY,
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    company         TEXT NOT NULL,
    role            TEXT NOT NULL,
    description     TEXT,
    start_date      DATE NOT NULL,
    end_date        DATE                         -- NULL = poste actuel
);

CREATE INDEX idx_experiences_portfolio ON portfolio_experiences (portfolio_id);


-- ----------------------------------------------------------------------------
-- 1.4 PORTFOLIO — CERTIFICATIONS
-- ----------------------------------------------------------------------------

CREATE TABLE portfolio_certifications (
    id                      UUID PRIMARY KEY,
    portfolio_id            UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    name                    TEXT NOT NULL,
    issuing_organization    TEXT NOT NULL,
    issue_date              DATE NOT NULL,
    expiry_date             DATE,
    credential_url          TEXT
);

CREATE INDEX idx_certifications_portfolio ON portfolio_certifications (portfolio_id);


-- ----------------------------------------------------------------------------
-- 1.5 CATEGORIES
-- ----------------------------------------------------------------------------

CREATE TABLE categories (
    id      UUID PRIMARY KEY,
    value   TEXT NOT NULL UNIQUE
);


-- ----------------------------------------------------------------------------
-- 1.6 SERVICES
-- ----------------------------------------------------------------------------

CREATE TABLE services (
    id              UUID PRIMARY KEY,
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL,               -- 'draft' | 'active' | 'paused' | 'deleted'
    category_id     UUID REFERENCES categories(id),

    -- Pricing (aplati)
    pricing_type    TEXT,                        -- 'fixed' | 'hourly' | 'range' | ...
    price_min       NUMERIC,
    price_max       NUMERIC,
    currency        TEXT,

    -- Embedding & reco
    embedding       BYTEA,                      -- embedding calculé depuis title + description + tags + category
    embedding_version TEXT,

    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_services_portfolio ON services (portfolio_id);
CREATE INDEX idx_services_category ON services (category_id);
CREATE INDEX idx_services_active ON services (status) WHERE status = 'active';


-- ----------------------------------------------------------------------------
-- 1.7 SERVICE — TAGS
-- ----------------------------------------------------------------------------

CREATE TABLE service_tags (
    service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    tag_id      UUID NOT NULL,
    value       TEXT NOT NULL,
    PRIMARY KEY (service_id, tag_id)
);

CREATE INDEX idx_service_tags_value ON service_tags (value);


-- ----------------------------------------------------------------------------
-- 1.8 SERVICE — AWARDS
-- ----------------------------------------------------------------------------

CREATE TABLE service_awards (
    service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    award_id    UUID NOT NULL,
    value       TEXT NOT NULL,
    PRIMARY KEY (service_id, award_id)
);


-- ----------------------------------------------------------------------------
-- 1.10 SERVICE — FAQS
-- ----------------------------------------------------------------------------
-- Stockées pour enrichir l'embedding (question + réponse = contexte sémantique)

CREATE TABLE service_faqs (
    id          UUID PRIMARY KEY,
    service_id  UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    question    TEXT NOT NULL,
    answer      TEXT NOT NULL
);

CREATE INDEX idx_faqs_service ON service_faqs (service_id);


-- ----------------------------------------------------------------------------
-- 1.11 JOB POSTS
-- ----------------------------------------------------------------------------

CREATE TABLE job_posts (
    id              UUID PRIMARY KEY,
    client_id       UUID NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL,               -- 'open' | 'closed' | 'draft'

    -- Budget (aplati)
    budget_type     TEXT,                        -- 'fixed' | 'hourly' | 'range'
    budget_min      NUMERIC,
    budget_max      NUMERIC,
    currency        TEXT,

    -- Embedding & reco
    embedding       BYTEA,
    embedding_version TEXT,

    created_at      TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_job_posts_client ON job_posts (client_id);
CREATE INDEX idx_job_posts_open ON job_posts (status) WHERE status = 'open';


-- ----------------------------------------------------------------------------
-- 1.12 REVIEWS (agrégées par service pour le scoring qualité)
-- ----------------------------------------------------------------------------

CREATE TABLE reviews (
    id              UUID PRIMARY KEY,
    service_id      UUID NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    reviewer_id     UUID NOT NULL,
    rating          NUMERIC NOT NULL,            -- ex: 1.0 à 5.0
    comment         TEXT,
    status          TEXT NOT NULL,               -- 'published' | 'hidden' | 'flagged'
    created_at      TIMESTAMPTZ
);

CREATE INDEX idx_reviews_service ON reviews (service_id) WHERE status = 'published';

-- Vue matérialisée pour les stats agrégées par service (refresh périodique)
CREATE MATERIALIZED VIEW service_review_stats AS
SELECT
    service_id,
    COUNT(*)            AS review_count,
    AVG(rating)         AS avg_rating,
    MIN(rating)         AS min_rating,
    MAX(rating)         AS max_rating
FROM reviews
WHERE status = 'published'
GROUP BY service_id;

CREATE UNIQUE INDEX idx_review_stats_service ON service_review_stats (service_id);

-- Vue matérialisée pour les stats agrégées par portfolio (refresh périodique)
CREATE MATERIALIZED VIEW portfolio_review_stats AS
SELECT
    s.portfolio_id,
    COUNT(r.id)         AS total_review_count,
    AVG(r.rating)       AS avg_rating
FROM reviews r
JOIN services s ON s.id = r.service_id
WHERE r.status = 'published'
GROUP BY s.portfolio_id;

CREATE UNIQUE INDEX idx_portfolio_review_stats ON portfolio_review_stats (portfolio_id);


-- ============================================================================
-- 2. TABLES PROPRES AU RECO (générées localement, pas de miroir .NET)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2.1 INTERACTIONS UTILISATEUR
-- ----------------------------------------------------------------------------

CREATE TABLE interactions (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID NOT NULL,
    item_type           TEXT NOT NULL,            -- 'service' | 'job_post'
    item_id             UUID NOT NULL,
    interaction_type    TEXT NOT NULL,            -- 'view' | 'like' | 'bookmark' | 'apply' | 'contact' | 'purchase' | 'dismiss'
    weight              NUMERIC NOT NULL,
    source              TEXT,                    -- 'feed' | 'search' | 'profile' | 'direct'
    position            INTEGER,                 -- position dans le feed (pour debiaiser)
    occurred_at         TIMESTAMPTZ NOT NULL,

    CONSTRAINT uq_interaction UNIQUE (user_id, item_id, interaction_type)
);

CREATE INDEX idx_interactions_user_recent ON interactions (user_id, occurred_at DESC);
CREATE INDEX idx_interactions_item ON interactions (item_id);


-- ----------------------------------------------------------------------------
-- 2.2 FOLLOWS (user suit un portfolio/freelancer)
-- ----------------------------------------------------------------------------

CREATE TABLE follows (
    user_id         UUID NOT NULL,
    portfolio_id    UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, portfolio_id)
);

CREATE INDEX idx_follows_portfolio ON follows (portfolio_id);


-- ----------------------------------------------------------------------------
-- 2.3 ITEMS REJETÉS (dismissed / "pas intéressé")
-- ----------------------------------------------------------------------------

CREATE TABLE dismissed_items (
    user_id     UUID NOT NULL,
    item_id     UUID NOT NULL,
    item_type   TEXT NOT NULL,
    dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, item_id)
);


-- ----------------------------------------------------------------------------
-- 2.4 AFFINITÉS UTILISATEUR — CATÉGORIES
-- ----------------------------------------------------------------------------

CREATE TABLE user_category_affinity (
    user_id         UUID NOT NULL,
    category_id     UUID NOT NULL REFERENCES categories(id),
    score           NUMERIC NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, category_id)
);


-- ----------------------------------------------------------------------------
-- 2.5 AFFINITÉS UTILISATEUR — TAGS
-- ----------------------------------------------------------------------------

CREATE TABLE user_tag_affinity (
    user_id         UUID NOT NULL,
    tag_value       TEXT NOT NULL,
    score           NUMERIC NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, tag_value)
);


-- ----------------------------------------------------------------------------
-- 2.6 AFFINITÉS UTILISATEUR — SKILLS
-- ----------------------------------------------------------------------------

CREATE TABLE user_skill_affinity (
    user_id         UUID NOT NULL,
    skill           TEXT NOT NULL,
    score           NUMERIC NOT NULL DEFAULT 0,
    interaction_count INTEGER NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, skill)
);


-- ----------------------------------------------------------------------------
-- 2.7 FEED IMPRESSIONS (pour mesurer la qualité du reco)
-- ----------------------------------------------------------------------------

CREATE TABLE feed_impressions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL,
    item_id     UUID NOT NULL,
    item_type   TEXT NOT NULL,
    position    INTEGER NOT NULL,
    score       NUMERIC,                        -- score de reco au moment du serving
    served_at   TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_impressions_user_time ON feed_impressions (user_id, served_at DESC);

-- Partitionnement par mois recommandé quand le volume grandit :
-- CREATE TABLE feed_impressions (...) PARTITION BY RANGE (served_at);


-- ----------------------------------------------------------------------------
-- 2.8 RECOMPUTE LOG (suivi des recalculs pour debugging & monitoring)
-- ----------------------------------------------------------------------------

CREATE TABLE recompute_log (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL,
    reason          TEXT NOT NULL,               -- 'interaction' | 'batch' | 'bootstrap' | 'manual'
    algo_version    TEXT NOT NULL,
    item_count      INTEGER NOT NULL,            -- nombre d'items dans le feed généré
    duration_ms     INTEGER NOT NULL,            -- temps de calcul
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_recompute_log_user ON recompute_log (user_id, computed_at DESC);


-- ============================================================================
-- 3. FONCTIONS UTILITAIRES
-- ============================================================================

-- Rafraîchir les stats de reviews (à appeler via cron toutes les heures)
-- REFRESH MATERIALIZED VIEW CONCURRENTLY service_review_stats;
-- REFRESH MATERIALIZED VIEW CONCURRENTLY portfolio_review_stats;


-- ============================================================================
-- 4. NOTES D'ARCHITECTURE
-- ============================================================================
--
-- TABLES MIROIR (section 1) :
--   - Alimentées UNIQUEMENT par les events RabbitMQ consommés par le sync worker
--   - Le champ synced_at permet de détecter les entités stale
--   - Les embeddings (BYTEA) sont calculés localement par le embedding worker
--   - Les données structurées sont conservées pour :
--     (a) filtrage SQL avant scoring
--     (b) boosts métier multiplicatifs
--     (c) recalcul d'embeddings lors de changement de modèle
--     (d) debugging et monitoring
--
-- TABLES RECO (section 2) :
--   - Générées localement par le microservice Python
--   - Les affinités sont incrémentées à chaque interaction
--   - Les impressions sont loggées pour mesurer le CTR
--   - Le recompute_log sert au monitoring et à l'optimisation
--
-- CONVENTIONS :
--   - Les value objects .NET (Pricing, Budget, etc.) sont aplatis en colonnes
--   - Les listes (tags, awards, skills) sont en tables jointes pour le querying
--   - Les enums .NET (status, type) sont stockés en TEXT pour la flexibilité
--   - Tous les UUID correspondent aux ID .NET — jamais de re-numérotation locale
--
-- REDIS (hors de cette base) :
--   - feed:user:{userId}           → Sorted Set (le feed précalculé, top 200)
--   - feed:anonymous:{categoryId}  → Sorted Set (fallback cold start)
--   - feed:anonymous:global        → Sorted Set (fallback ultime)
--   - recompute_lock:{userId}      → String avec TTL 30s (debouncing)
--