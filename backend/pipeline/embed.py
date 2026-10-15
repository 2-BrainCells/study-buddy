"""BGE-M3 embeddings on CPU, shared by the pipeline and the API."""

from functools import lru_cache

EMBED_MODEL = "BAAI/bge-m3"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import (
        SentenceTransformer,
    )  # torch is slow to import; load on first use

    return SentenceTransformer(EMBED_MODEL, device="cpu")


def embed(texts: list[str]) -> list[list[float]]:
    """Normalized 1024-dim vectors, so cosine similarity is a dot product."""
    return _model().encode(texts, normalize_embeddings=True).tolist()


def to_vector(v: list[float]) -> str:
    """pgvector text format '[0.1,0.2,...]' (avoids adding the pgvector package)."""
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
