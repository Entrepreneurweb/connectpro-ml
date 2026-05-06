
import logging
from datetime import datetime, date, timezone

from asyncpg import Connection

logger = logging.getLogger(__name__)


def parse_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


async def upsert_category(conn: Connection, data: dict) -> None:
    await conn.execute(
        """
        INSERT INTO categories (id, value)
        VALUES ($1, $2)
        ON CONFLICT (id) DO UPDATE SET value = EXCLUDED.value
        """,
        data["id"],
        data["value"],
    )
    logger.info(" Category upserted — id=%s, value=%s", data["id"], data["value"])



async def upsert_portfolio(conn: Connection, data: dict) -> None:
    async with conn.transaction():
        general = data.get("general_info") or {}
        location = data.get("location_info") or {}
        professional = data.get("professional_info") or {}
        contact = data.get("contact_info") or {}

        await conn.execute(
            """
            INSERT INTO portfolios (
                id, owner_id, type, status,
                first_name, last_name, bio,
                country, city, timezone,
                headline,
                website_url,
                active_services_count,
                synced_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
            ON CONFLICT (id) DO UPDATE SET
                owner_id = EXCLUDED.owner_id,
                type = EXCLUDED.type,
                status = EXCLUDED.status,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                bio = EXCLUDED.bio,
                country = EXCLUDED.country,
                city = EXCLUDED.city,
                timezone = EXCLUDED.timezone,
                headline = EXCLUDED.headline,
                website_url = EXCLUDED.website_url,
                active_services_count = EXCLUDED.active_services_count,
                profile_embedding = NULL,
                synced_at = NOW()
            """,
            data["id"],
            data["owner_id"],
            data.get("type", "freelancer"),
            data.get("status", "active"),
            general.get("first_name"),
            general.get("last_name"),
            general.get("bio"),
            location.get("country"),
            location.get("city"),
            location.get("timezone"),
            professional.get("headline"),
            contact.get("website_url"),
            data.get("active_services_count", 0),
        )

        portfolio_id = data["id"]


        skills = professional.get("skills") or []
        await conn.execute("DELETE FROM portfolio_skills WHERE portfolio_id = $1", portfolio_id)
        if skills:
            await conn.executemany(
                "INSERT INTO portfolio_skills (portfolio_id, skill) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                [(portfolio_id, s) for s in skills],
            )

        experiences = data.get("experiences") or []
        await conn.execute("DELETE FROM portfolio_experiences WHERE portfolio_id = $1", portfolio_id)
        if experiences:
            await conn.executemany(
                """
                INSERT INTO portfolio_experiences (id, portfolio_id, company, role, description, start_date, end_date)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        exp["id"],
                        portfolio_id,
                        exp["company"],
                        exp["role"],
                        exp.get("description"),
                        parse_date(exp["start_date"]),
                        parse_date(exp.get("end_date")),
                    )
                    for exp in experiences
                ],
            )


        certifications = data.get("certifications") or []
        await conn.execute("DELETE FROM portfolio_certifications WHERE portfolio_id = $1", portfolio_id)
        if certifications:
            await conn.executemany(
                """
                INSERT INTO portfolio_certifications (
                    id, portfolio_id, name, issuing_organization,
                    issue_date, expiry_date, credential_url
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        cert["id"],
                        portfolio_id,
                        cert["name"],
                        cert["issuing_organization"],
                        parse_date(cert["issue_date"]),
                        parse_date(cert.get("expiry_date")),
                        cert.get("credential_url"),
                    )
                    for cert in certifications
                ],
            )

    logger.info(
        " Portfolio upserted — id=%s, skills=%d, exp=%d, certs=%d",
        portfolio_id, len(skills), len(experiences), len(certifications),
    )


async def upsert_service(conn: Connection, data: dict) -> None:
    async with conn.transaction():
        pricing = data.get("pricing") or {}

        await conn.execute(
            """
            INSERT INTO services (
                id, portfolio_id, title, description, status, category_id,
                pricing_type, price_min, price_max, currency,
                created_at, updated_at, synced_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
            ON CONFLICT (id) DO UPDATE SET
                portfolio_id = EXCLUDED.portfolio_id,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                status = EXCLUDED.status,
                category_id = EXCLUDED.category_id,
                pricing_type = EXCLUDED.pricing_type,
                price_min = EXCLUDED.price_min,
                price_max = EXCLUDED.price_max,
                currency = EXCLUDED.currency,
                updated_at = EXCLUDED.updated_at,
                embedding = CASE
                    WHEN services.title != EXCLUDED.title
                      OR services.description != EXCLUDED.description
                    THEN NULL
                    ELSE services.embedding
                END,
                synced_at = NOW()
            """,
            data["id"],
            data.get("portfolio_id"),
            data["title"],
            data["description"],
            data.get("status", "active"),
            data.get("category_id"),
            pricing.get("type"),
            pricing.get("price_min"),
            pricing.get("price_max"),
            pricing.get("currency"),
            parse_timestamp(data.get("created_at")),
            parse_timestamp(data.get("updated_at")),
        )

        service_id = data["id"]


        tags = data.get("tags") or []
        await conn.execute("DELETE FROM service_tags WHERE service_id = $1", service_id)
        if tags:
            await conn.executemany(
                "INSERT INTO service_tags (service_id, tag_id, value) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                [(service_id, t["id"], t["value"]) for t in tags],
            )


        awards = data.get("awards") or []
        await conn.execute("DELETE FROM service_awards WHERE service_id = $1", service_id)
        if awards:
            await conn.executemany(
                "INSERT INTO service_awards (service_id, award_id, value) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                [(service_id, a["id"], a["value"]) for a in awards],
            )


        faqs = data.get("faqs") or []
        await conn.execute("DELETE FROM service_faqs WHERE service_id = $1", service_id)
        if faqs:
            await conn.executemany(
                "INSERT INTO service_faqs (id, service_id, question, answer) VALUES ($1, $2, $3, $4)",
                [(f["id"], service_id, f["question"], f["answer"]) for f in faqs],
            )

    logger.info(
        " Service upserted — id=%s, title=%s, tags=%d, awards=%d, faqs=%d",
        service_id, data["title"], len(tags), len(awards), len(faqs),
    )


async def update_service_status(conn: Connection, service_id: str, new_status: str) -> None:
    await conn.execute(
        "UPDATE services SET status = $1, synced_at = NOW() WHERE id = $2",
        new_status, service_id,
    )
    logger.info(" Service status updated — id=%s → %s", service_id, new_status)


async def delete_service(conn: Connection, service_id: str) -> None:
    await conn.execute("DELETE FROM services WHERE id = $1", service_id)
    logger.info(" Service deleted — id=%s (CASCADE: tags, awards, faqs)", service_id)



async def upsert_job_post(conn: Connection, data: dict) -> None:
    budget = data.get("budget") or {}

    await conn.execute(
        """
        INSERT INTO job_posts (
            id, client_id, title, description, status,
            budget_type, budget_min, budget_max, currency,
            created_at, updated_at, synced_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
        ON CONFLICT (id) DO UPDATE SET
            client_id = EXCLUDED.client_id,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            status = EXCLUDED.status,
            budget_type = EXCLUDED.budget_type,
            budget_min = EXCLUDED.budget_min,
            budget_max = EXCLUDED.budget_max,
            currency = EXCLUDED.currency,
            updated_at = EXCLUDED.updated_at,
            embedding = CASE
                WHEN job_posts.title != EXCLUDED.title
                  OR job_posts.description != EXCLUDED.description
                THEN NULL
                ELSE job_posts.embedding
            END,
            synced_at = NOW()
        """,
        data["id"],
        data["client_id"],
        data["title"],
        data["description"],
        data.get("status", "open"),
        budget.get("type"),
        budget.get("budget_min"),
        budget.get("budget_max"),
        budget.get("currency"),
        parse_timestamp(data.get("created_at")),
        parse_timestamp(data.get("updated_at")),
    )
    logger.info(" JobPost upserted — id=%s, title=%s", data["id"], data["title"])


async def update_job_post_status(conn: Connection, job_post_id: str, new_status: str) -> None:
    await conn.execute(
        "UPDATE job_posts SET status = $1, synced_at = NOW() WHERE id = $2",
        new_status, job_post_id,
    )
    logger.info(" JobPost status updated — id=%s → %s", job_post_id, new_status)



async def upsert_review(conn: Connection, data: dict) -> None:
    await conn.execute(
        """
        INSERT INTO reviews (id, service_id, reviewer_id, rating, comment, status, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (id) DO UPDATE SET
            rating = EXCLUDED.rating,
            comment = EXCLUDED.comment,
            status = EXCLUDED.status
        """,
        data["id"],
        data["service_id"],
        data["reviewer_id"],
        data["rating"],
        data.get("comment"),
        data.get("status", "published"),
        parse_timestamp(data.get("created_at")),
    )
    logger.info(" Review upserted — id=%s, service=%s, rating=%s", data["id"], data["service_id"], data["rating"])