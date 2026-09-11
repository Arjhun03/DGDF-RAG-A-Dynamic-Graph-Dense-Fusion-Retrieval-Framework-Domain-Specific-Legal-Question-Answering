import json
import logging
from pathlib import Path
from .config import settings
from .neo4j_store import neo4j_store
from .pinecone_store import pinecone_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_databases")


def main():
    print("=" * 65)
    print("DGDF-RAG: PINECONE & NEO4J SEED & SYNCHRONIZATION UTILITY")
    print("=" * 65)

    base_dir = Path(__file__).resolve().parents[2] / "data"
    chunks_file = base_dir / "chunks.json"
    graph_file = base_dir / "graph.json"

    # 1. Check Pinecone
    print("\n[1/2] Checking Pinecone Vector Database...")
    pc_health = pinecone_store.health_check()
    print(f"Status: {'CONNECTED' if pc_health.get('connected') else 'DISCONNECTED'}")
    print(f"Index: {pc_health.get('index')} | Vectors: {pc_health.get('total_vector_count')}")

    if pc_health.get("connected"):
        if pc_health.get("total_vector_count", 0) == 0 and chunks_file.exists():
            print("Pinecone index is empty. Uploading chunks...")
            with open(chunks_file, "r", encoding="utf-8") as f:
                chunks_data = json.load(f)
            chunks_list = chunks_data if isinstance(chunks_data, list) else chunks_data.get("chunks", [])
            print(f"Found {len(chunks_list)} chunks to upload.")
            for start in range(0, len(chunks_list), 100):
                batch = chunks_list[start : start + 100]
                pinecone_store.upsert_chunks(batch)
                print(f"Uploaded {min(start + 100, len(chunks_list))}/{len(chunks_list)}")
            print("Pinecone indexing complete.")
        else:
            print(f"Pinecone already contains {pc_health.get('total_vector_count')} vectors.")
    else:
        print(f"Pinecone connection error: {pc_health.get('error')}")

    # 2. Sync to Neo4j
    print("\n[2/2] Checking Neo4j Graph Database...")
    neo_health = neo4j_store.health_check()
    print(f"Status: {'CONNECTED' if neo_health.get('connected') else 'DISCONNECTED'}")
    print(f"Database: {neo_health.get('database')} | Nodes: {neo_health.get('nodes')} | Relationships: {neo_health.get('relationships')}")

    if neo_health.get("connected"):
        if graph_file.exists():
            print(f"Loading local knowledge graph from {graph_file}...")
            with open(graph_file, "r", encoding="utf-8") as f:
                graph_data = json.load(f)

            node_count = len(graph_data.get("nodes", []))
            edge_count = len(graph_data.get("edges", []))
            print(f"Found {node_count} nodes and {edge_count} edges to sync into Neo4j Aura.")

            res = neo4j_store.sync_graph(graph_data, batch_size=100)
            print(f"Sync successful! Neo4j now has synced nodes and relationships.")

            updated_health = neo4j_store.health_check()
            print(f"Updated Neo4j stats: {updated_health.get('nodes')} nodes, {updated_health.get('relationships')} relationships.")
        else:
            print("graph.json not found. Run rebuild_graph() first.")
    else:
        print(f"Neo4j connection error: {neo_health.get('error')}")

    print("\n" + "=" * 65)
    print("DATABASE SEEDING & SYNCHRONIZATION COMPLETE!")
    print("=" * 65)


if __name__ == "__main__":
    main()
