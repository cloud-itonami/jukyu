"""jukyu `rankCompanyExposure` graph — read `mv_jukyu_company_exposure_rank`.

NSID: com.etzhayyim.apps.jukyu.rankCompanyExposure
Filters: domain, countryCode, minRiskScore; limit 250.
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
    min_risk_score: float | None
    scenario_id: str | None
    limit: int
    companies: list[dict[str, Any]]
    total: int
    error: str | None


async def _node_query(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"error": "RW_URL not set", "companies": []}
    limit = max(1, min(250, int(state.get("limit") or 50)))
    domain = state.get("domain")
    country = state.get("country_code")
    min_risk = state.get("min_risk_score") or 0.0

    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            params: list[Any] = [float(min_risk)]
            where_parts = ["risk_score >= %s"]
            if domain:
                where_parts.append("domain = %s")
                params.append(domain)
            if country:
                where_parts.append("country_code = %s")
                params.append(country)
            where = "WHERE " + " AND ".join(where_parts)
            await cur.execute(
                f"""
                SELECT company_did, company_name, domain, country_code,
                       risk_score, supply_pressure, demand_pressure,
                       price_pressure, downstream_pressure, structural_pressure,
                       confidence, recommended_action, status
                FROM mv_jukyu_company_exposure_rank
                {where}
                ORDER BY risk_score DESC
                LIMIT {int(limit)}
                """,
                params,
            )
            rows = await cur.fetchall()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("rankCompanyExposure failed")
        return {"error": f"query: {exc!s}"[:300], "companies": []}

    companies = [
        {
            "companyDid": r[0],
            "companyName": r[1] or "",
            "domain": r[2],
            "countryCode": r[3] or "",
            "riskScore": float(r[4] or 0),
            "supplyPressure": float(r[5] or 0),
            "demandPressure": float(r[6] or 0),
            "pricePressure": float(r[7] or 0),
            "downstreamPressure": float(r[8] or 0),
            "structuralPressure": float(r[9] or 0),
            "confidence": float(r[10] or 0),
            "recommendedAction": r[11] or "",
            "status": r[12] or "active",
        }
        for r in rows
    ]
    return {"companies": companies, "total": len(companies)}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.rankCompanyExposure",
        object_id=f"rankCompanyExposure:{int(time.time())}",
        object_type="jukyu.companyExposure",
        attributes={"returned": state.get("total", 0), "domain": state.get("domain")},
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("query", _node_query, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("audit", _node_audit)
    g.add_edge(START, "query")
    g.add_edge("query", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="rank_company_exposure")
