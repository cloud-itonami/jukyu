"""jukyu resident 15-min equilibrium loop graph.

Cron: */15 * * * * (with_llm=false for cost efficiency)
Runs the full Pregel cycle for all domains without LLM enrichment.
Triggered by langgraph.json crons section.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from lg_jukyu.audit import emit_audit_bg

_log = logging.getLogger(__name__)

_RW_URL = os.environ.get("RW_URL") or os.environ.get("LG_CHECKPOINTER_URL", "")
_APP_DID = os.environ.get("JUKYU_APP_DID", "did:web:jukyu.etzhayyim.com")

_RISK_WEIGHTS = {
    "supply": 0.30, "demand": 0.20, "price": 0.20,
    "downstream": 0.20, "structural": 0.10,
}


class _State(TypedDict, total=False):
    run_id: str
    with_llm: bool
    shock_seeds: dict[str, float]
    max_iterations: int
    balance_rows: list[dict[str, Any]]
    supply_nodes: list[dict[str, Any]]
    supply_edges: list[dict[str, Any]]
    node_scores: dict[str, dict[str, float]]
    superstep: int
    converged: bool
    company_exposures: list[dict[str, Any]]
    signals_written: int
    outbox_count: int
    error: str | None


async def _node_init(state: _State) -> dict[str, Any]:
    run_id = f"jukyu.equil.{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    return {
        "run_id": run_id,
        "superstep": 0,
        "converged": False,
        "shock_seeds": {},
        "max_iterations": 8,
        "with_llm": bool(state.get("with_llm", False)),
    }


async def _node_read_balance(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"balance_rows": []}
    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            await cur.execute(
                """
                SELECT domain, country_code, product_family,
                       supply_quantity, demand_quantity, inventory_quantity,
                       balance_quantity, avg_confidence, latest_observed_at
                FROM mv_jukyu_global_balance
                LIMIT 10000
                """
            )
            rows = await cur.fetchall()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.warning("equil read_balance failed: %s", exc)
        return {"balance_rows": []}

    return {
        "balance_rows": [
            {
                "domain": r[0], "countryCode": r[1], "productFamily": r[2],
                "supplyQuantity": float(r[3] or 0), "demandQuantity": float(r[4] or 0),
                "inventoryQuantity": float(r[5] or 0), "balanceQuantity": float(r[6] or 0),
                "confidence": float(r[7] or 0), "latestObservedAt": str(r[8] or ""),
            }
            for r in rows
        ]
    }


async def _node_read_chain(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"supply_nodes": [], "supply_edges": []}
    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            await cur.execute(
                """
                SELECT vertex_id, node_code, node_kind, domain, country_code, operator_did,
                       supply_capacity, demand_capacity
                FROM vertex_jukyu_supply_node
                LIMIT 20000
                """
            )
            nodes_raw = await cur.fetchall()
            await cur.execute(
                """
                SELECT src_vid, dst_vid, relationship,
                       capacity_quantity, dependency_weight, confidence
                FROM edge_jukyu_supply_dependency
                LIMIT 100000
                """
            )
            edges_raw = await cur.fetchall()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.warning("equil read_chain failed: %s", exc)
        return {"supply_nodes": [], "supply_edges": []}

    return {
        "supply_nodes": [
            {
                "nodeId": r[0], "nodeCode": r[1], "nodeKind": r[2],
                "domain": r[3], "countryCode": r[4], "operatorDid": r[5] or "",
                "supplyCapacity": float(r[6] or 0),
                "demandCapacity": float(r[7] or 0),
                "confidence": 0.5,
            }
            for r in nodes_raw
        ],
        "supply_edges": [
            {
                "src": r[0], "dst": r[1], "relationship": r[2],
                "capacityQuantity": float(r[3] or 0),
                "dependencyWeight": float(r[4] or 0), "confidence": float(r[5] or 0),
            }
            for r in edges_raw
        ],
    }


async def _node_propagate(state: _State) -> dict[str, Any]:
    supply_nodes = state.get("supply_nodes") or []
    supply_edges = state.get("supply_edges") or []
    balance_rows = state.get("balance_rows") or []
    max_iter = state.get("max_iterations") or 8

    upstream: dict[str, list[dict[str, Any]]] = {}
    for e in supply_edges:
        dst = e.get("dst", "")
        if dst not in upstream:
            upstream[dst] = []
        upstream[dst].append(e)

    balance_index: dict[str, dict[str, Any]] = {}
    for b in balance_rows:
        key = f"{b.get('domain','')}.{b.get('countryCode','')}"
        balance_index[key] = b

    node_scores: dict[str, dict[str, float]] = {}
    for n in supply_nodes:
        nid = n.get("nodeId", "")
        dom = n.get("domain", "")
        cc = n.get("countryCode", "")
        bal = balance_index.get(f"{dom}.{cc}", {})
        supply_t = float(n.get("supplyCapacity") or 1)
        demand_t = float(n.get("demandCapacity") or supply_t)
        imbalance = max(0, (demand_t - supply_t) / max(supply_t, 1))
        node_scores[nid] = {
            "supply": min(1.0, imbalance),
            "demand": float(bal.get("demandQuantity", 0)) / max(float(bal.get("supplyQuantity", 1)), 1) if bal else 0,
            "price": 0.0, "downstream": 0.0, "structural": 0.0,
            "confidence": float(n.get("confidence") or 0.5),
        }

    stable_count = superstep = 0
    for superstep in range(max_iter):
        new_scores: dict[str, dict[str, float]] = {}
        max_delta = 0.0
        for nid, scores in node_scores.items():
            up_edges = upstream.get(nid, [])
            upstream_p = 0.0
            for e in up_edges:
                src = e.get("src", "")
                if src in node_scores:
                    src_risk = _compute_risk(node_scores[src])
                    w = float(e.get("dependencyWeight", 0.5))
                    c = float(e.get("confidence", 0.5))
                    upstream_p += src_risk * w * c
            if up_edges:
                upstream_p = min(1.0, upstream_p / len(up_edges))
            new = dict(scores)
            new["supply"] = min(1.0, scores.get("supply", 0) + upstream_p * 0.5)
            new["downstream"] = min(1.0, upstream_p)
            max_delta = max(max_delta, abs(_compute_risk(new) - _compute_risk(scores)))
            new_scores[nid] = new
        node_scores = new_scores
        stable_count = (stable_count + 1) if max_delta < 0.03 else 0
        if stable_count >= 2:
            break

    company_map: dict[str, list[dict[str, float]]] = {}
    node_by_id = {n.get("nodeId", ""): n for n in supply_nodes}
    for nid, scores in node_scores.items():
        op = node_by_id.get(nid, {}).get("operatorDid", "")
        if not op:
            continue
        if op not in company_map:
            company_map[op] = []
        company_map[op].append({**scores, "risk": _compute_risk(scores)})

    company_exposures = []
    for op, node_list in company_map.items():
        n = len(node_list)
        company_exposures.append({
            "companyDid": op,
            "riskScore": round(sum(x["risk"] for x in node_list) / n, 4),
            "supplyPressure": round(sum(x.get("supply", 0) for x in node_list) / n, 4),
            "demandPressure": round(sum(x.get("demand", 0) for x in node_list) / n, 4),
            "confidence": round(sum(x.get("confidence", 0.5) for x in node_list) / n, 4),
            "nodeCount": n,
        })
    company_exposures.sort(key=lambda x: x["riskScore"], reverse=True)
    return {
        "node_scores": node_scores,
        "company_exposures": company_exposures,
        "superstep": superstep + 1,
        "converged": stable_count >= 2,
    }


def _compute_risk(s: dict[str, float]) -> float:
    return s.get("supply", 0)*0.30 + s.get("demand", 0)*0.20 + s.get("price", 0)*0.20 + s.get("downstream", 0)*0.20 + s.get("structural", 0)*0.10


async def _node_write_signals(state: _State) -> dict[str, Any]:
    exposures = state.get("company_exposures") or []
    run_id = state.get("run_id", "")
    if not _RW_URL:
        return {"signals_written": 0}
    written = 0
    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            for ce in exposures:
                risk = float(ce.get("riskScore", 0))
                if risk < 0.4:
                    continue
                severity = "critical" if risk >= 0.8 else "high" if risk >= 0.6 else "medium"
                signal_id = f"jukyu-equil:{time.strftime('%Y%m%d')}:{ce.get('companyDid','?')[:30]}"
                vertex_id = f"at://jukyu001.etzhayyim.com/com.etzhayyim.apps.jukyu.notificationSignal/{uuid.uuid4().hex[:12]}"
                await cur.execute(
                    "DELETE FROM vertex_jukyu_notification_signal WHERE signal_id = %s",
                    (signal_id,),
                )
                await cur.execute(
                    """
                    INSERT INTO vertex_jukyu_notification_signal
                        (vertex_id, signal_id, target_company_did, run_id,
                         risk_score, confidence, severity, domain,
                         recommended_action, notification_status,
                         emitted_at, created_date, actor_did, org_did)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'global',
                            'Review supply chain exposure', 'pending', NOW(), CURRENT_DATE,
                            %s, 'anon')
                    """,
                    (vertex_id, signal_id, ce.get("companyDid"), run_id,
                     risk, float(ce.get("confidence", 0)), severity, _APP_DID),
                )
                written += 1
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.warning("equil write_signals failed: %s", exc)
    return {"signals_written": written}


async def _node_read_outbox_count(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"outbox_count": 0}
    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            await cur.execute(
                "SELECT COUNT(*) FROM vertex_jukyu_notification_signal WHERE delivery_status = 'pending'"
            )
            row = await cur.fetchone()
            count = int((row or [0])[0])
        finally:
            await conn.close()
    except Exception:
        count = 0
    return {"outbox_count": count}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.equilibrium.run",
        object_id=state.get("run_id", "unknown"),
        object_type="jukyu.pregelRun",
        attributes={
            "superstep": state.get("superstep", 0),
            "converged": state.get("converged", False),
            "signalsWritten": state.get("signals_written", 0),
            "outboxCount": state.get("outbox_count", 0),
            "companyCount": len(state.get("company_exposures") or []),
        },
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("init", _node_init)
    g.add_node("read_balance", _node_read_balance, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("read_chain", _node_read_chain, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("propagate", _node_propagate)
    g.add_node("write_signals", _node_write_signals, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("read_outbox_count", _node_read_outbox_count)
    g.add_node("audit", _node_audit)

    g.add_edge(START, "init")
    g.add_edge("init", "read_balance")
    g.add_edge("read_balance", "read_chain")
    g.add_edge("read_chain", "propagate")
    g.add_edge("propagate", "write_signals")
    g.add_edge("write_signals", "read_outbox_count")
    g.add_edge("read_outbox_count", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="equilibrium")
