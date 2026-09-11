import json
import sys
from pathlib import Path

from .pinecone_store import pinecone_store


def load_chunks() -> list[dict]:
    """
    Load the existing DGDF-RAG chunks from data/chunks.json.
    """

    project_root = Path(__file__).resolve().parents[2]
    chunks_file = project_root / "data" / "chunks.json"

    if not chunks_file.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {chunks_file}"
        )

    with open(chunks_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        chunks = data.get("chunks", [])
    else:
        chunks = data

    return chunks


def upload_chunks(
    chunks: list[dict],
    batch_size: int = 80,
) -> None:
    """
    Upload chunks to Pinecone in batches.
    """
    total = len(chunks)
    print(f"Total chunks: {total}", flush=True)

    uploaded = 0
    for start in range(0, total, batch_size):
        batch = chunks[start:start + batch_size]
        pinecone_store.upsert_chunks(batch)
        uploaded += len(batch)
        print(f"Uploaded {uploaded}/{total}", flush=True)

    print("\nPINECONE INDEXING COMPLETE", flush=True)


def main():
    print("=" * 60)
    print("DGDF-RAG → PINECONE INDEXER")
    print("=" * 60)
    print()

    chunks = load_chunks()

    if not chunks:
        print("ERROR: No chunks found.")
        sys.exit(1)

    # Safety validation before uploading.
    article_21 = [
        chunk
        for chunk in chunks
        if str(chunk.get("article", "")) == "21"
    ]

    print(
        f"Article 21 chunks found: {len(article_21)}"
    )

    if len(article_21) != 1:
        print(
            "ERROR: Expected exactly 1 Article 21 chunk."
        )
        sys.exit(1)

    article_21_chunk = article_21[0]

    print(
        "Article 21 page:",
        article_21_chunk.get("page"),
    )

    print()

    if "--yes" in sys.argv or "-y" in sys.argv or not sys.stdin.isatty():
        answer = "y"
    else:
        answer = input(
            "Upload these chunks to Pinecone? [y/N]: "
        )

    if answer.lower() != "y":
        print("Upload cancelled.")
        return

    print()
    # The namespace is already clean because the test data
    # was removed before indexing.
    #
    # Do not call clear_namespace() here because Pinecone
    # returns 404 when the namespace does not exist yet.

    print("Uploading Constitution chunks...")
    print()

    upload_chunks(chunks)

    print()
    print(
        pinecone_store.health_check()
    )


if __name__ == "__main__":
    main()