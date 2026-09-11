import logging
from .document_processor import extract_entities
from .storage import chunks, replace_graph

logger = logging.getLogger(__name__)


def rebuild_graph():
    nodes = []
    edges = []
    index = {}

    def get_node(entity_type, value, chunk_id=None, extra_props=None):
        entity_type = str(entity_type).strip()
        value = str(value).strip()
        if not value:
            return None
        key = (entity_type.lower(), value.lower())
        if key not in index:
            node_obj = {
                "id": f"{entity_type}:{value}",
                "type": entity_type,
                "value": value,
                "chunk_ids": [],
            }
            if extra_props:
                node_obj.update(extra_props)
            index[key] = node_obj
            nodes.append(node_obj)

        if chunk_id and chunk_id not in index[key]["chunk_ids"]:
            index[key]["chunk_ids"].append(chunk_id)
        return index[key]["id"]

    # Core Constitutional Root Nodes
    doc_id = get_node("Document", "Constitution of India")
    part3_id = get_node("Part", "Part III", extra_props={"title": "Fundamental Rights"})
    edges.append({
        "source": doc_id,
        "target": part3_id,
        "relation": "contains",
        "chunk_id": "",
    })

    # Add core rights
    liberty_right_id = get_node("Right", "Life and Personal Liberty")
    edu_right_id = get_node("Right", "Right to Education")
    equality_right_id = get_node("Right", "Equality before Law")

    for chunk in chunks():
        chunk_id = chunk.get("id")
        if not chunk_id:
            continue

        chunk_type = chunk.get("chunk_type")
        part = chunk.get("part")
        page = chunk.get("page", 0)

        # Skip schedule enclaves/tables from generating false article entities
        if page > 467 or chunk_type in ("schedule_entry", "schedule_paragraph"):
            continue

        art_num = chunk.get("article_number") or chunk.get("article")
        sec_num = chunk.get("section")
        clause_num = chunk.get("clause") or chunk.get("clause_number")
        rule_num = chunk.get("rule")
        act_num = chunk.get("act")

        art_node_id = None
        if art_num and chunk_type == "constitutional_article":
            art_title = chunk.get("article_title") or chunk.get("heading")
            art_node_id = get_node("Article", str(art_num).upper(), chunk_id, extra_props={
                "title": art_title,
                "part": part or "Part III",
            })
            if part == "Part III" and part3_id and art_node_id:
                edges.append({
                    "source": part3_id,
                    "target": art_node_id,
                    "relation": "contains",
                    "chunk_id": chunk_id,
                })

        # Specific Rights linkage
        if art_num == "21" and art_node_id:
            edges.append({
                "source": art_node_id,
                "target": liberty_right_id,
                "relation": "protects",
                "chunk_id": chunk_id,
            })
        elif art_num == "21A" and art_node_id:
            edges.append({
                "source": art_node_id,
                "target": edu_right_id,
                "relation": "protects",
                "chunk_id": chunk_id,
            })
        elif art_num == "14" and art_node_id:
            edges.append({
                "source": art_node_id,
                "target": equality_right_id,
                "relation": "protects",
                "chunk_id": chunk_id,
            })

        # Generic entity extraction for other entities in text
        entities = extract_entities(chunk.get("text", ""))
        chunk_entity_ids = []
        if art_node_id:
            chunk_entity_ids.append(art_node_id)

        for ent in entities:
            e_type = ent["type"]
            e_val = ent["value"]
            if e_type == "Article" and not (chunk_type == "constitutional_article"):
                continue
            nid = get_node(e_type, e_val, chunk_id)
            if nid and nid not in chunk_entity_ids:
                chunk_entity_ids.append(nid)

        for i in range(len(chunk_entity_ids)):
            for j in range(i + 1, min(len(chunk_entity_ids), i + 4)):
                edges.append({
                    "source": chunk_entity_ids[i],
                    "target": chunk_entity_ids[j],
                    "relation": "related_to",
                    "chunk_id": chunk_id,
                })

    # Explicit relationship between Article 21 and 21A
    a21_key = ("article", "21")
    a21a_key = ("article", "21a")
    if a21_key in index and a21a_key in index:
        edges.append({
            "source": index[a21_key]["id"],
            "target": index[a21a_key]["id"],
            "relation": "amendment_extension",
            "chunk_id": "",
        })
        edges.append({
            "source": index[a21a_key]["id"],
            "target": index[a21_key]["id"],
            "relation": "derived_from",
            "chunk_id": "",
        })

    # Deduplicate edges
    dedup = []
    seen_edges = set()
    for edge in edges:
        key = (
            edge["source"],
            edge["target"],
            edge["relation"],
        )
        if key not in seen_edges and edge["source"] != edge["target"]:
            seen_edges.add(key)
            dedup.append(edge)

    result = {"nodes": nodes, "edges": dedup}
    replace_graph(result)
    logger.info(f"Local graph rebuilt: {len(nodes)} nodes, {len(dedup)} edges.")

    # Synchronize to Neo4j
    try:
        from .neo4j_store import neo4j_store
        if neo4j_store.is_connected:
            neo4j_store.sync_graph(result)
            logger.info("Successfully synced graph to Neo4j Aura.")
    except Exception as e:
        logger.error(f"Failed to sync graph to Neo4j: {e}")

    return result
