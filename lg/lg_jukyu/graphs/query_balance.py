"""jukyu `queryBalance` graph — read `mv_jukyu_global_balance`.

NSID: com.etzhayyim.apps.jukyu.queryBalance
Filters: domain, countryCode, productFamily; limit 500.
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
    time_window: str | None
    limit: int
    rows: list[dict[str, Any]]
    total: int
    error: str | None


async def _node_query(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"error": "RW_URL not set", "rows": []}
    limit = max(1, min(500, int(state.get("limit") or 100)))
    domain = state.get("domain")
    country = state.get("country_code")
    product = state.get("product_family")

    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            params: list[Any] = []
            where_parts: list[str] = []
            if domain:
                where_parts.append("domain = %s")
                params.append(domain)
            if country:
                where_parts.append("country_code = %s")
                params.append(country)
            if product:
                where_parts.append("product_family = %s")
                params.append(product)
            where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
            await cur.execute(
                f"""
                SELECT domain, country_code, product_family,
                       supply_quantity, demand_quantity, inventory_quantity,
                       balance_quantity, avg_confidence, latest_observed_at,
                       observation_count
                FROM mv_jukyu_global_balance
                {where}
                ORDER BY domain, country_code, product_family
                LIMIT {int(limit)}
                """,
                params,
            )
            rows_raw = await cur.fetchall()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("queryBalance failed")
        return {"error": f"query: {exc!s}"[:300], "rows": []}

    rows = [
        {
            "domain": r[0],
            "countryCode": r[1],
            "productFamily": r[2],
            "supplyQuantity": float(r[3] or 0),
            "demandQuantity": float(r[4] or 0),
            "inventoryQuantity": float(r[5] or 0),
            "balanceQuantity": float(r[6] or 0),
            "confidence": float(r[7] or 0),
            "latestObservedAt": str(r[8] or ""),
            "observationCount": int(r[9] or 0),
        }
        for r in rows_raw
    ]
    return {"rows": rows, "total": len(rows)}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.queryBalance",
        object_id=f"queryBalance:{int(time.time())}",
        object_type="jukyu.balance",
        attributes={"returned": state.get("total", 0), "domain": state.get("domain")},
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("query", _node_query, retry_policy=RetryPolicy(max_attempts=3, backoff_factor=1.5))
    g.add_node("audit", _node_audit)
    g.add_edge(START, "query")
    g.add_edge("query", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="query_balance")
