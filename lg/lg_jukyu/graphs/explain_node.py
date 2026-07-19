"""jukyu `explainNode` graph — node + upstream chain (50) + balance (10).

NSID: com.etzhayyim.apps.jukyu.explainNode
Required: nodeCode.
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
    node_code: str
    node: dict[str, Any] | None
    chain: list[dict[str, Any]]
    balance: list[dict[str, Any]]
    company_exposure: dict[str, Any] | None
    error: str | None


async def _node_fetch(state: _State) -> dict[str, Any]:
    node_code = state.get("node_code", "").strip()
    if not node_code:
        return {"error": "node_code is required"}
    if not _RW_URL:
        return {"error": "RW_URL not set"}

    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()

            # Fetch the node itself
            await cur.execute(
                """
                SELECT node_code, node_kind, domain, country_code,
                       operator_did, supply_capacity, demand_capacity,
                       display_name, status, source_table
                FROM vertex_jukyu_supply_node
                WHERE node_code = %s
                LIMIT 1
                """,
                (node_code,),
            )
            row = await cur.fetchone()
            if not row:
                return {"error": f"node not found: {node_code}", "chain": [], "balance": []}

            node = {
                "nodeCode": row[0], "nodeKind": row[1], "domain": row[2],
                "countryCode": row[3], "operatorDid": row[4] or "",
                "supplyCapacity": float(row[5] or 0),
                "demandCapacity": float(row[6] or 0),
                "displayName": row[7] or "", "status": row[8] or "",
                "sourceTable": row[9] or "",
            }

            # Upstream chain via mv_jukyu_supply_chain_trace (50 edges)
            await cur.execute(
                """
                SELECT edge_id, relationship, src_node_code, src_name,
                       src_country_code, dst_node_code, dst_name,
                       capacity_quantity, dependency_weight, confidence
                FROM mv_jukyu_supply_chain_trace
                WHERE dst_node_code = %s
                ORDER BY dependency_weight DESC
                LIMIT 50
                """,
                (node_code,),
            )
            chain_rows = await cur.fetchall()
            chain = [
                {
                    "edgeId": r[0], "relationship": r[1],
                    "srcNodeCode": r[2], "srcName": r[3] or "",
                    "srcCountryCode": r[4] or "",
                    "dstNodeCode": r[5], "dstName": r[6] or "",
                    "capacityQuantity": float(r[7] or 0),
                    "dependencyWeight": float(r[8] or 0),
                    "confidence": float(r[9] or 0),
                }
                for r in chain_rows
            ]

            # Balance from MV (10 rows for this node's domain/country)
            await cur.execute(
                """
                SELECT domain, country_code, product_family,
                       supply_quantity, demand_quantity, balance_quantity,
                       avg_confidence, latest_observed_at, observation_count
                FROM mv_jukyu_global_balance
                WHERE domain = %s AND country_code = %s
                ORDER BY latest_observed_at DESC
                LIMIT 10
                """,
                (node["domain"], node["countryCode"] or "XX"),
            )
            bal_rows = await cur.fetchall()
            balance = [
                {
                    "domain": r[0], "countryCode": r[1], "productFamily": r[2],
                    "supplyQuantity": float(r[3] or 0), "demandQuantity": float(r[4] or 0),
                    "balanceQuantity": float(r[5] or 0),
                    "confidence": float(r[6] or 0), "latestObservedAt": str(r[7] or ""),
                    "observationCount": int(r[8] or 0),
                }
                for r in bal_rows
            ]

            # Company exposure for this node's operator
            operator = node.get("operatorDid")
            company_exposure = None
            if operator:
                await cur.execute(
                    """
                    SELECT company_did, risk_score, confidence, status
                    FROM mv_jukyu_company_exposure_rank
                    WHERE company_did = %s
                    LIMIT 1
                    """,
                    (operator,),
                )
                ce_row = await cur.fetchone()
                if ce_row:
                    company_exposure = {
                        "companyDid": ce_row[0],
                        "riskScore": float(ce_row[1] or 0),
                        "confidence": float(ce_row[2] or 0),
                        "status": ce_row[3] or "active",
                    }
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("explainNode failed for %s", node_code)
        return {"error": f"query: {exc!s}"[:300], "chain": [], "balance": []}

    return {"node": node, "chain": chain, "balance": balance, "company_exposure": company_exposure}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.explainNode",
        object_id=state.get("node_code", "unknown"),
        object_type="jukyu.supplyNode",
        attributes={"chainLen": len(state.get("chain", [])), "balanceLen": len(state.get("balance", []))},
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("fetch", _node_fetch, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("audit", _node_audit)
    g.add_edge(START, "fetch")
    g.add_edge("fetch", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="explain_node")
