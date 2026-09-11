import logging
from typing import Any, Optional
from neo4j import GraphDatabase, Driver
from .config import settings

logger = logging.getLogger(__name__)


class Neo4jStore:
    """
    Neo4j persistent graph database store for DGDF-RAG.
    Stores legal entities (Articles, Sections, Clauses, Rules, Acts)
    and relationships (CONTAINS, RELATED_TO) for relationship-aware retrieval.
    """

    def __init__(self):
        self._driver: Optional[Driver] = None
        self._database = settings.neo4j_database or "neo4j"
        self._init_driver()

    def _init_driver(self):
        if not settings.neo4j_uri or not settings.neo4j_password:
            logger.warning("Neo4j credentials not configured. Neo4j graph store disabled.")
            return

        try:
            self._driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
                max_connection_lifetime=3600,
            )
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j driver: {e}")
            self._driver = None

    @property
    def is_connected(self) -> bool:
        if not self._driver:
            return False
        try:
            with self._driver.session(database=self._database) as session:
                res = session.run("RETURN 1 as val").single()
                return res is not None and res["val"] == 1
        except Exception:
            return False

    def health_check(self) -> dict[str, Any]:
        if not self._driver:
            return {
                "connected": False,
                "error": "Driver not initialized or credentials missing",
                "nodes": 0,
                "relationships": 0,
            }

        try:
            with self._driver.session(database=self._database) as session:
                node_count = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
                rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
                labels = session.run("CALL db.labels() YIELD label RETURN collect(label) as labels").single()["labels"]
                return {
                    "connected": True,
                    "database": self._database,
                    "nodes": int(node_count),
                    "relationships": int(rel_count),
                    "labels": labels,
                }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "nodes": 0,
                "relationships": 0,
            }

    def init_schema(self):
        """Create uniqueness constraints and indexes for legal entities."""
        if not self._driver:
            return

        queries = [
            "CREATE CONSTRAINT legal_entity_id IF NOT EXISTS FOR (e:LegalEntity) REQUIRE e.id IS UNIQUE",
            "CREATE INDEX legal_entity_type_value IF NOT EXISTS FOR (e:LegalEntity) ON (e.type, e.value)",
        ]
        try:
            with self._driver.session(database=self._database) as session:
                for q in queries:
                    session.run(q)
        except Exception as e:
            logger.warning(f"Error creating Neo4j schema: {e}")

    def sync_graph(self, graph_data: dict[str, Any], batch_size: int = 100) -> dict[str, int]:
        """
        Synchronize full graph nodes and edges into Neo4j.
        """
        if not self._driver:
            return {"nodes": 0, "relationships": 0}

        self.init_schema()

        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])

        # 1. Upsert Nodes in batches
        node_query = """
        UNWIND $batch AS item
        MERGE (e:LegalEntity {id: item.id})
        SET e.type = item.type,
            e.value = item.value,
            e.chunk_ids = item.chunk_ids
        """

        with self._driver.session(database=self._database) as session:
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i : i + batch_size]
                session.run(node_query, batch=batch)

            # Also apply specific secondary labels (e.g. :Article, :Section)
            fallback_label_query = """
            UNWIND $batch AS item
            MATCH (e:LegalEntity {id: item.id})
            FOREACH (_ IN CASE WHEN toLower(item.type) = 'article' THEN [1] ELSE [] END | SET e:Article)
            FOREACH (_ IN CASE WHEN toLower(item.type) = 'section' THEN [1] ELSE [] END | SET e:Section)
            FOREACH (_ IN CASE WHEN toLower(item.type) = 'clause' THEN [1] ELSE [] END | SET e:Clause)
            FOREACH (_ IN CASE WHEN toLower(item.type) = 'rule' THEN [1] ELSE [] END | SET e:Rule)
            FOREACH (_ IN CASE WHEN toLower(item.type) = 'act' THEN [1] ELSE [] END | SET e:Act)
            """
            for i in range(0, len(nodes), batch_size):
                batch = nodes[i : i + batch_size]
                try:
                    session.run(fallback_label_query, batch=batch)
                except Exception as e:
                    logger.debug(f"Label tagging notice: {e}")

            # 2. Upsert Edges in batches
            edge_query = """
            UNWIND $batch AS item
            MATCH (s:LegalEntity {id: item.source})
            MATCH (t:LegalEntity {id: item.target})
            FOREACH (_ IN CASE WHEN toLower(item.relation) = 'contains' THEN [1] ELSE [] END |
                MERGE (s)-[r:CONTAINS]->(t)
                SET r.relation = 'contains', r.chunk_id = item.chunk_id
            )
            FOREACH (_ IN CASE WHEN toLower(item.relation) <> 'contains' THEN [1] ELSE [] END |
                MERGE (s)-[r:RELATED_TO]->(t)
                SET r.relation = item.relation, r.chunk_id = item.chunk_id
            )
            """
            for i in range(0, len(edges), batch_size):
                batch = edges[i : i + batch_size]
                session.run(edge_query, batch=batch)

        logger.info(f"Synced {len(nodes)} nodes and {len(edges)} edges to Neo4j.")
        return {"nodes": len(nodes), "relationships": len(edges)}

    def search(
        self,
        query_references: dict[str, list[str]],
        query_tokens: set[str],
        top_k: int = 10,
        depth: int = 1,
        intent: str = "definition",
    ) -> list[dict[str, Any]]:
        """
        Traverse graph in Neo4j based on references, query tokens, and intent depth.
        Supports 1-hop lookups and 2-3 hop relationship/comparison traversals.
        """
        if not self._driver:
            return []

        # Build list of exact references to search
        exact_pairs = []
        for ref_type, values in query_references.items():
            single_type = ref_type.rstrip("s").capitalize()
            for v in values:
                exact_pairs.append({"type": single_type.lower(), "value": str(v).strip().lower()})

        token_list = list(query_tokens)

        # Multi-entity relational path search if multiple references present
        if len(exact_pairs) >= 2 and intent in ("RELATIONSHIP", "COMPARISON"):
            multi_hop_cypher = """
            MATCH (a:LegalEntity), (b:LegalEntity)
            WHERE toLower(a.value) = $val1 AND toLower(b.value) = $val2
            OPTIONAL MATCH p = (a)-[r*1..3]-(b)
            UNWIND relationships(p) AS rel
            RETURN startNode(rel).id AS edge_source,
                   endNode(rel).id AS edge_target,
                   startNode(rel).type AS node_type,
                   startNode(rel).value AS node_value,
                   startNode(rel).chunk_ids AS node_chunks,
                   coalesce(rel.relation, type(rel)) AS rel_name,
                   coalesce(rel.chunk_id, '') AS rel_chunk_id,
                   1.0 AS score
            LIMIT $top_k
            """
            try:
                with self._driver.session(database=self._database) as session:
                    res = session.run(
                        multi_hop_cypher,
                        val1=exact_pairs[0]["value"],
                        val2=exact_pairs[1]["value"],
                        top_k=top_k,
                    )
                    multi_paths = []
                    for record in res:
                        src = record["edge_source"]
                        tgt = record["edge_target"]
                        if src and tgt:
                            multi_paths.append({
                                "score": 1.0,
                                "node": {
                                    "id": src,
                                    "type": record["node_type"] or "Entity",
                                    "value": record["node_value"] or "",
                                    "chunk_ids": record["node_chunks"] or [],
                                },
                                "edge": {
                                    "source": src,
                                    "target": tgt,
                                    "relation": record["rel_name"] or "related_to",
                                    "chunk_id": record["rel_chunk_id"] or "",
                                },
                            })
                    if multi_paths:
                        return multi_paths
            except Exception as e:
                logger.debug(f"Multi-hop Cypher fallback notice: {e}")

        # Standard adaptive 1-hop / 2-hop traversal
        if depth >= 2:
            cypher = """
            MATCH (n:LegalEntity)
            WHERE (size($exact_pairs) > 0 AND ANY(p IN $exact_pairs WHERE toLower(n.type) = p.type AND toLower(n.value) = p.value))
               OR (size($tokens) > 0 AND ANY(t IN $tokens WHERE toLower(n.value) CONTAINS t))
            WITH n,
                 CASE
                   WHEN ANY(p IN $exact_pairs WHERE toLower(n.type) = p.type AND toLower(n.value) = p.value) THEN 1.0
                   ELSE 0.5
                 END AS score
            ORDER BY score DESC
            LIMIT $top_k

            OPTIONAL MATCH (n)-[r1]-(m:LegalEntity)
            OPTIONAL MATCH (m)-[r2]-(k:LegalEntity)
            WITH n, score, coalesce(r2, r1) AS r, coalesce(k, m) AS target_node
            RETURN n.id AS node_id,
                   n.type AS node_type,
                   n.value AS node_value,
                   n.chunk_ids AS node_chunks,
                   score,
                   startNode(r).id AS edge_source,
                   endNode(r).id AS edge_target,
                   type(r) AS rel_type,
                   r.relation AS rel_name,
                   r.chunk_id AS rel_chunk_id
            """
        else:
            cypher = """
            MATCH (n:LegalEntity)
            WHERE (size($exact_pairs) > 0 AND ANY(p IN $exact_pairs WHERE toLower(n.type) = p.type AND toLower(n.value) = p.value))
               OR (size($tokens) > 0 AND ANY(t IN $tokens WHERE toLower(n.value) CONTAINS t))
            WITH n,
                 CASE
                   WHEN ANY(p IN $exact_pairs WHERE toLower(n.type) = p.type AND toLower(n.value) = p.value) THEN 1.0
                   ELSE 0.5
                 END AS score
            ORDER BY score DESC
            LIMIT $top_k

            OPTIONAL MATCH (n)-[r]-(m:LegalEntity)
            RETURN n.id AS node_id,
                   n.type AS node_type,
                   n.value AS node_value,
                   n.chunk_ids AS node_chunks,
                   score,
                   startNode(r).id AS edge_source,
                   endNode(r).id AS edge_target,
                   type(r) AS rel_type,
                   r.relation AS rel_name,
                   r.chunk_id AS rel_chunk_id
            """

        paths = []
        try:
            with self._driver.session(database=self._database) as session:
                results = session.run(
                    cypher,
                    exact_pairs=exact_pairs,
                    tokens=token_list[:20],
                    top_k=top_k,
                )
                for record in results:
                    node_id = record["node_id"]
                    if not node_id:
                        continue
                    node_obj = {
                        "id": node_id,
                        "type": record["node_type"] or "Entity",
                        "value": record["node_value"] or "",
                        "chunk_ids": record["node_chunks"] or [],
                    }
                    score = float(record["score"] or 0.0)

                    edge_source = record["edge_source"]
                    edge_target = record["edge_target"]
                    if edge_source and edge_target:
                        edge_obj = {
                            "source": edge_source,
                            "target": edge_target,
                            "relation": record["rel_name"] or record["rel_type"] or "related_to",
                            "chunk_id": record["rel_chunk_id"] or "",
                        }
                    else:
                        edge_obj = {
                            "source": node_id,
                            "target": node_id,
                            "relation": "self",
                            "chunk_id": "",
                        }

                    paths.append({
                        "score": score,
                        "node": node_obj,
                        "edge": edge_obj,
                    })
        except Exception as e:
            logger.error(f"Neo4j graph search error: {e}")
            return []

        return paths

    def get_full_graph(self, limit_nodes: int = 300, limit_edges: int = 500) -> dict[str, list]:
        """Fetch active graph for UI visualization."""
        if not self._driver:
            return {"nodes": [], "edges": []}

        cypher = """
        MATCH (n:LegalEntity)
        WITH n LIMIT $limit_nodes
        OPTIONAL MATCH (n)-[r]->(m:LegalEntity)
        RETURN collect(DISTINCT {
            id: n.id,
            type: n.type,
            value: n.value,
            chunk_ids: n.chunk_ids
        }) as nodes,
        collect(DISTINCT {
            source: startNode(r).id,
            target: endNode(r).id,
            relation: coalesce(r.relation, type(r)),
            chunk_id: coalesce(r.chunk_id, '')
        }) as edges
        """
        try:
            with self._driver.session(database=self._database) as session:
                rec = session.run(cypher, limit_nodes=limit_nodes, limit_edges=limit_edges).single()
                if rec:
                    raw_nodes = rec["nodes"] or []
                    raw_edges = [e for e in (rec["edges"] or []) if e.get("source") and e.get("target")]
                    return {"nodes": raw_nodes, "edges": raw_edges}
        except Exception as e:
            logger.error(f"Error fetching full graph from Neo4j: {e}")

        return {"nodes": [], "edges": []}

    def delete_document(self, document_id: str):
        """Remove entities or relationships associated with a document."""
        if not self._driver or not document_id:
            return
        # Cypher to remove relationships created for chunks of this document
        # And delete any orphan nodes
        cypher = """
        MATCH ()-[r]->()
        WHERE r.chunk_id STARTS WITH $doc_id
        DELETE r
        """
        try:
            with self._driver.session(database=self._database) as session:
                session.run(cypher, doc_id=document_id)
        except Exception as e:
            logger.warning(f"Error pruning document relations from Neo4j: {e}")

    def clear_database(self):
        """Clear all nodes and relationships in Neo4j."""
        if not self._driver:
            return
        try:
            with self._driver.session(database=self._database) as session:
                session.run("MATCH (n) DETACH DELETE n")
        except Exception as e:
            logger.error(f"Error clearing Neo4j database: {e}")

    def close(self):
        if self._driver:
            self._driver.close()


neo4j_store = Neo4jStore()
