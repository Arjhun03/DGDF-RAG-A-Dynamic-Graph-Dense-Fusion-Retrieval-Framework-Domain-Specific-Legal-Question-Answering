from typing import Any

from pinecone import Pinecone

from .config import settings


class PineconeStore:
    """
    Pinecone storage and semantic-search layer for DGDF-RAG.

    The Pinecone index uses:
        - Integrated embedding model: multilingual-e5-large
        - Text field: text
        - Metric: cosine
    """

    def __init__(self):
        self.client = None
        self.index = None
        self.namespace = settings.pinecone_namespace or "default"
        self._init_client()

    def _init_client(self):
        if not settings.pinecone_api_key or not settings.pinecone_index_name:
            return

        try:
            self.client = Pinecone(api_key=settings.pinecone_api_key)
            self.index = self.client.Index(settings.pinecone_index_name)
        except Exception as e:
            self.client = None
            self.index = None

    @property
    def is_connected(self) -> bool:
        if self.index is None:
            return False
        try:
            self.index.describe_index_stats()
            return True
        except Exception:
            return False

    # ---------------------------------------------------------
    # HEALTH CHECK
    # ---------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """
        Check Pinecone connectivity and return basic index statistics.
        """
        if self.index is None:
            return {
                "connected": False,
                "error": "Pinecone not configured or driver uninitialized",
                "index": settings.pinecone_index_name,
                "namespace": self.namespace,
                "total_vector_count": 0,
            }

        try:
            stats = self.index.describe_index_stats()
            return {
                "connected": True,
                "index": settings.pinecone_index_name,
                "namespace": self.namespace,
                "total_vector_count": stats.total_vector_count,
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "index": settings.pinecone_index_name,
                "namespace": self.namespace,
                "total_vector_count": 0,
            }

    # ---------------------------------------------------------
    # UPSERT CHUNKS
    # ---------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> None:
        """
        Upload document chunks to Pinecone.
        """
        if not self.index or not chunks:
            return

        records = []
        for chunk in chunks:
            chunk_id = str(
                chunk.get("id")
                or chunk.get("chunk_id")
                or ""
            )
            text = str(
                chunk.get("text")
                or ""
            ).strip()

            if not chunk_id or not text:
                continue

            record = {
                "_id": chunk_id,
                "text": text,
                "document": str(chunk.get("document") or "Constitution of India"),
                "document_type": str(chunk.get("document_type") or "constitution"),
                "part": str(chunk.get("part") or ""),
                "chapter": str(chunk.get("chapter") or ""),
                "document_id": str(chunk.get("document_id") or ""),
                "page": int(chunk.get("page") or 0),
                "article": str(chunk.get("article") or ""),
                "article_number": str(chunk.get("article_number") or chunk.get("article") or ""),
                "article_title": str(chunk.get("article_title") or chunk.get("heading") or ""),
                "section": str(chunk.get("section") or ""),
                "clause": str(chunk.get("clause") or ""),
                "chunk_type": str(chunk.get("chunk_type") or "text"),
                "authority_level": int(chunk.get("authority_level") or 5),
            }
            records.append(record)

        if not records:
            return

        batch_size = 80
        import logging
        logger = logging.getLogger(__name__)

        import time
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            for attempt in range(4):
                try:
                    self.index.upsert_records(
                        namespace=self.namespace,
                        records=batch,
                    )
                    break
                except Exception as e:
                    err_msg = str(e).lower()
                    if "429" in err_msg or "resource_exhausted" in err_msg:
                        logger.warning(f"Pinecone rate limit 429 on batch {i}..{i+len(batch)}, backing off 6s (attempt {attempt+1}/4)...")
                        time.sleep(6)
                    else:
                        logger.error(f"Pinecone upsert error (records {i}..{i+len(batch)}): {e}")
                        break

    # ---------------------------------------------------------
    # SEMANTIC SEARCH
    # ---------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Perform semantic search using Pinecone's integrated multilingual-e5-large model.
        """
        if not self.index:
            return []

        query = query.strip()
        if not query:
            return []

        try:
            response = self.index.search(
                namespace=self.namespace,
                query={
                    "inputs": {
                        "text": query,
                    },
                    "top_k": top_k,
                },
                fields=[
                    "text",
                    "document",
                    "document_type",
                    "part",
                    "chapter",
                    "document_id",
                    "page",
                    "article",
                    "article_number",
                    "article_title",
                    "section",
                    "clause",
                    "chunk_type",
                    "authority_level",
                ],
            )

            matches = []
            for hit in response.result.hits:
                fields = hit.fields or {}
                matches.append(
                    {
                        "id": hit.id,
                        "score": float(hit.score if hit.score is not None else 0.0),
                        "text": fields.get("text", ""),
                        "document": fields.get("document", "Constitution of India"),
                        "document_type": fields.get("document_type", "constitution"),
                        "part": fields.get("part", ""),
                        "chapter": fields.get("chapter", ""),
                        "document_id": fields.get("document_id", ""),
                        "page": fields.get("page", 0),
                        "article": fields.get("article", ""),
                        "article_number": fields.get("article_number", fields.get("article", "")),
                        "article_title": fields.get("article_title", ""),
                        "heading": fields.get("article_title", ""),
                        "section": fields.get("section", ""),
                        "clause": fields.get("clause", ""),
                        "chunk_type": fields.get("chunk_type", ""),
                        "authority_level": fields.get("authority_level", 5),
                    }
                )
            return matches
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Pinecone search error: {e}")
            return []

    # ---------------------------------------------------------
    # DELETE DOCUMENT
    # ---------------------------------------------------------

    def delete_document(
        self,
        document_id: str,
    ) -> None:
        """
        Delete all Pinecone records belonging to a particular document.
        """
        if not self.index or not document_id:
            return

        try:
            self.index.delete(
                namespace=self.namespace,
                filter={
                    "document_id": document_id,
                },
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Pinecone delete error: {e}")

    # ---------------------------------------------------------
    # CLEAR NAMESPACE
    # ---------------------------------------------------------

    def clear_namespace(self) -> None:
        """
        Delete all records from the configured
        Pinecone namespace.

        Use carefully.
        """

        self.index.delete(
            namespace=self.namespace,
            delete_all=True,
        )


# -------------------------------------------------------------
# SINGLETON INSTANCE
# -------------------------------------------------------------

pinecone_store = PineconeStore()