"""jukyu `querySupplyChain` graph — read `mv_jukyu_supply_chain_trace`.

NSID: com.etzhayyim.apps.jukyu.querySupplyChain
Filters: domain, countryCode, productFamily, nodeCode; limit 1000.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from lg_jukyu.audit import emit_audit_bg

_log = logging.getLogger(__name__)

_RW_URL = os.environ.get("RW_URL") or os.environ.get("LG_CHECKPOINTER_URL", "")
_APP_DID = os.environ.get("JUKYU_APP_DID", "did:web:jukyu.etzhayyim.com")


class _State(TypedDict, total=False):
    domain: str | None
    country_code: str | None
    product_family: str | None
    node_code: str | None
    seed_country: str | None
    max_hops: int | None
    include_downstream: bool | None
    limit: int
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    total_nodes: int
    total_edges: int
    error: str | None


async def _node_query_nodes(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"error": "RW_URL not set", "nodes": [], "edges": []}
    limit = max(1, min(1000, int(state.get("limit") or 200)))
    domain = state.get("domain")
    country = state.get("country_code") or state.get("seed_country")
    product = state.get("product_family")
    node_code = state.get("node_code")

    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()

            # Query mv_jukyu_supply_chain_trace — one row per edge with embedded src/dst node info
            params: list[Any] = []
            where: list[str] = []
            if domain:
                where.append("domain = %s")
                params.append(domain)
            if country:
                where.append("(src_country_code = %s OR dst_country_code = %s)")
                params.extend([country, country])
            if product:
                where.append("product_family = %s")
                params.append(product)
            if node_code:
                where.append("(src_node_code = %s OR dst_node_code = %s)")
                params.extend([node_code, node_code])
            w = ("WHERE " + " AND ".join(where)) if where else ""
            await cur.execute(
                f"""
                SELECT edge_id, domain, relationship,
                       src_vid, src_node_code, src_node_kind, src_name,
                       src_country_code, src_operator_did,
                       dst_vid, dst_node_code, dst_node_kind, dst_name,
                       dst_country_code, dst_operator_did,
                       capacity_quantity, dependency_weight, confidence
                FROM mv_jukyu_supply_chain_trace
                {w}
                ORDER BY dependency_weight DESC
                LIMIT {int(limit)}
                """,
                params,
            )
            rows = await cur.fetchall()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("querySupplyChain failed")
        return {"error": f"query: {exc!s}"[:300], "nodes": [], "edges": []}

    # Extract unique nodes from src/dst
    seen_nodes: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for r in rows:
        for vid, code, kind, name, cc, op in [
            (r[3], r[4], r[5], r[6], r[7], r[8]),
            (r[9], r[10], r[11], r[12], r[13], r[14]),
        ]:
            if vid not in seen_nodes:
                seen_nodes.add(vid)
                nodes.append({
                    "nodeId": vid, "nodeCode": code, "nodeKind": kind,
                    "displayName": name or "", "countryCode": cc or "",
                    "operatorDid": op or "",
                })

    edges = [
        {
            "edgeId": r[0], "domain": r[1], "relationship": r[2],
            "srcVid": r[3], "dstVid": r[9],
            "capacityQuantity": float(r[15] or 0),
            "dependencyWeight": float(r[16] or 0),
            "confidence": float(r[17] or 0),
        }
        for r in rows
    ]
    return {"nodes": nodes, "edges": edges, "total_nodes": len(nodes), "total_edges": len(edges)}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.querySupplyChain",
        object_id=f"querySupplyChain:{int(time.time())}",
        object_type="jukyu.supplyChain",
        attributes={
            "totalNodes": state.get("total_nodes", 0),
            "totalEdges": state.get("total_edges", 0),
            "domain": state.get("domain"),
        },
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("query_nodes", _node_query_nodes, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("audit", _node_audit)
    g.add_edge(START, "query_nodes")
    g.add_edge("query_nodes", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="query_supply_chain")
