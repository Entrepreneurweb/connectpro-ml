
import logging
import numpy as np
from sentence_transformers import SentenceTransformer
import os

logger = logging.getLogger(__name__)


# evite les requtet
os.environ["HF_HUB_OFFLINE"] = "1"

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_VERSION = "minilm-v1"

_model: SentenceTransformer | None = None


def load_model() -> None:

    global _model
    logger.info(" Chargement du modèle d'embedding — %s ...", MODEL_NAME)
    _model = SentenceTransformer(MODEL_NAME)
    logger.info(" Modèle chargé — dimensions=%d", _model.get_embedding_dimension())


def get_model() -> SentenceTransformer:
    if _model is None:
        raise RuntimeError("Le modèle d'embedding n'est pas chargé.")
    return _model


def compute_embedding(text: str) -> bytes:

    model = get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.astype(np.float32).tobytes()


def build_service_text(
    title: str,
    description: str,
    tags: list[str] | None = None,
    category_name: str | None = None,
    faqs: list[dict] | None = None,
) -> str:

    parts = [title, description]

    if tags:
        parts.append(" ".join(tags))

    if category_name:
        parts.append(category_name)

    if faqs:
        for faq in faqs:
            parts.append(f"{faq.get('question', '')} {faq.get('answer', '')}")

    return ". ".join(p for p in parts if p)


def build_portfolio_text(
    headline: str | None = None,
    bio: str | None = None,
    skills: list[str] | None = None,
    experiences: list[dict] | None = None,
) -> str:

    parts = []

    if headline:
        parts.append(headline)

    if bio:
        parts.append(bio)

    if skills:
        parts.append(" ".join(skills))

    if experiences:
        for exp in experiences:
            role = exp.get("role", "")
            company = exp.get("company", "")
            desc = exp.get("description", "")
            parts.append(f"{role} {company} {desc}".strip())

    return ". ".join(p for p in parts if p)


def build_job_post_text(
    title: str,
    description: str,
) -> str:

    return f"{title}. {description}"