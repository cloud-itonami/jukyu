"""jukyu `runStressPropagation` graph — Pregel equilibrium propagation.

NSID: com.etzhayyim.apps.jukyu.runStressPropagation
Graph: jukyu_global_equilibrium_v1

7 supersteps per JUKYU_DESIGN.md:
  1. read_balance     — load mv_jukyu_global_balance
  2. read_chain       — load supply nodes + edges
  3. parse_scenario   — (optional) LLM parse scenarioText → shocks
  4. propagate        — bounded Pregel: score each node, pass messages
  5. write_signals    — persist company exposures + notification outbox
  6. enrich_signals   — (optional, withLLM) LLM title/body/action
  7. read_outbox      — return pending signals

Risk score: 0.30×supply + 0.20×demand + 0.20×price + 0.20×downstream + 0.10×structural
Confidence: freshness(30%) + reliability(25%) + connectivity(20%) + cargo/price(15%) + corroboration(10%)
Halting: max 8 supersteps; stop if max delta < 0.03 for 2 consecutive supersteps.
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
_LLM_URL = os.environ.get("JUKYU_LLM_URL", "http://llm.etzhayyim.com")
_LLM_API_KEY = os.environ.get("JUKYU_LLM_API_KEY", "")
_EXTRACTION_MODEL = os.environ.get("JUKYU_LLM_EXTRACTION_MODEL", "qwen3-30b")
_NARRATIVE_MODEL = os.environ.get("JUKYU_LLM_NARRATIVE_MODEL", "gemma-4-e4b-it")
_LLM_TIMEOUT = float(os.environ.get("JUKYU_LLM_TIMEOUT", "30"))
_ENRICH_MAX = int(os.environ.get("JUKYU_LLM_ENRICH_MAX", "10"))

_RISK_WEIGHTS = {
    "supply": 0.30, "demand": 0.20, "price": 0.20,
    "downstream": 0.20, "structural": 0.10,
}


class _State(TypedDict, total=False):
    run_id: str
    domain: str | None
    with_llm: bool
    scenario_text: str | None
    shock_seeds: dict[str, float]
    max_iterations: int
    # intermediate
    balance_rows: list[dict[str, Any]]
    supply_nodes: list[dict[str, Any]]
    supply_edges: list[dict[str, Any]]
    parsed_shocks: list[dict[str, Any]]
    node_scores: dict[str, dict[str, float]]
    superstep: int
    converged: bool
    company_exposures: list[dict[str, Any]]
    signals_written: int
    signals_enriched: int
    outbox: list[dict[str, Any]]
    error: str | None
    latency_ms: int


async def _node_init_run(state: _State) -> dict[str, Any]:
    run_id = f"jukyu.global.{state.get('domain','all')}.{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    return {
        "run_id": run_id,
        "superstep": 0,
        "converged": False,
        "shock_seeds": state.get("shock_seeds") or {},
        "max_iterations": min(8, int(state.get("max_iterations") or 8)),
    }


async def _node_read_balance(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"balance_rows": []}
    domain = state.get("domain")
    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            params: list[Any] = []
            where = ""
            if domain:
                where = "WHERE domain = %s"
                params.append(domain)
            await cur.execute(
                f"""
                SELECT domain, country_code, product_family,
                       supply_quantity, demand_quantity, inventory_quantity,
                       balance_quantity, avg_confidence, latest_observed_at
                FROM mv_jukyu_global_balance
                {where}
                LIMIT 5000
                """,
                params,
            )
            rows = await cur.fetchall()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("read_balance failed")
        return {"balance_rows": [], "error": f"read_balance: {exc!s}"[:200]}

    balance_rows = [
        {
            "domain": r[0], "countryCode": r[1], "productFamily": r[2],
            "supplyQuantity": float(r[3] or 0), "demandQuantity": float(r[4] or 0),
            "inventoryQuantity": float(r[5] or 0), "balanceQuantity": float(r[6] or 0),
            "confidence": float(r[7] or 0), "latestObservedAt": str(r[8] or ""),
        }
        for r in rows
    ]
    return {"balance_rows": balance_rows}


async def _node_read_chain(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"supply_nodes": [], "supply_edges": []}
    domain = state.get("domain")
    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            params_n: list[Any] = []
            where_n = ""
            if domain:
                where_n = "WHERE domain = %s"
                params_n.append(domain)
            await cur.execute(
                f"""
                SELECT vertex_id, node_code, node_kind, domain, country_code, operator_did,
                       supply_capacity, demand_capacity
                FROM vertex_jukyu_supply_node
                {where_n}
                LIMIT 10000
                """,
                params_n,
            )
            nodes_raw = await cur.fetchall()

            await cur.execute(
                """
                SELECT src_vid, dst_vid, relationship,
                       capacity_quantity, dependency_weight, substitution_difficulty,
                       confidence
                FROM edge_jukyu_supply_dependency
                LIMIT 50000
                """,
            )
            edges_raw = await cur.fetchall()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("read_chain failed")
        return {"supply_nodes": [], "supply_edges": [], "error": f"read_chain: {exc!s}"[:200]}

    supply_nodes = [
        {
            "nodeId": r[0], "nodeCode": r[1], "nodeKind": r[2],
            "domain": r[3], "countryCode": r[4],
            "operatorDid": r[5] or "",
            "supplyCapacity": float(r[6] or 0),
            "demandCapacity": float(r[7] or 0),
            "confidence": 0.5,
        }
        for r in nodes_raw
    ]
    supply_edges = [
        {
            "src": r[0], "dst": r[1], "relationship": r[2],
            "capacityQuantity": float(r[3] or 0), "dependencyWeight": float(r[4] or 0),
            "substitutionDifficulty": float(r[5] or 0), "confidence": float(r[6] or 0),
        }
        for r in edges_raw
    ]
    return {"supply_nodes": supply_nodes, "supply_edges": supply_edges}


async def _node_parse_scenario(state: _State) -> dict[str, Any]:
    scenario_text = state.get("scenario_text", "")
    with_llm = state.get("with_llm", False)
    shock_seeds = dict(state.get("shock_seeds") or {})

    if not scenario_text or not with_llm:
        return {"parsed_shocks": []}

    try:
        import httpx
        headers = {"Content-Type": "application/json"}
        if _LLM_API_KEY:
            headers["Authorization"] = f"Bearer {_LLM_API_KEY}"
        prompt = (
            f"Extract supply-demand shock events from the following text.\n"
            f"Return JSON array with fields: shock_type, domain, country_code, severity (0-1), "
            f"duration_days, description.\n\nText:\n{scenario_text}"
        )
        payload = {
            "model": _EXTRACTION_MODEL,
            "messages": [
                {"role": "system", "content": "You are a commodity supply-chain analyst. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
            resp = await client.post(f"{_LLM_URL}/v1/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # Parse JSON from content
        import json, re
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            shocks = json.loads(match.group())
        else:
            shocks = []
        # Merge into shock_seeds
        for shock in shocks:
            key = f"{shock.get('domain','')}.{shock.get('country_code','')}"
            shock_seeds[key] = max(shock_seeds.get(key, 0), float(shock.get("severity", 0)))
        return {"parsed_shocks": shocks, "shock_seeds": shock_seeds}
    except Exception as exc:  # noqa: BLE001
        _log.warning("parse_scenario LLM call failed (non-fatal): %s", exc)
        return {"parsed_shocks": []}


async def _node_propagate(state: _State) -> dict[str, Any]:
    """Bounded Pregel propagation across supply chain graph."""
    supply_nodes = state.get("supply_nodes") or []
    supply_edges = state.get("supply_edges") or []
    balance_rows = state.get("balance_rows") or []
    shock_seeds = state.get("shock_seeds") or {}
    max_iter = state.get("max_iterations") or 8

    # Build adjacency: dst → [(src, edge)]
    upstream: dict[str, list[dict[str, Any]]] = {}
    for e in supply_edges:
        dst = e.get("dst", "")
        if dst not in upstream:
            upstream[dst] = []
        upstream[dst].append(e)

    # Build balance index: (domain, country) → balance row
    balance_index: dict[str, dict[str, Any]] = {}
    for b in balance_rows:
        key = f"{b.get('domain','')}.{b.get('countryCode','')}"
        balance_index[key] = b

    # Domain reliability priors (confidence formula: reliability component, weight=0.25).
    _DOMAIN_RELIABILITY: dict[str, float] = {
        "naphtha": 0.72, "crude_oil": 0.60, "semiconductor": 0.60,
        "energy": 0.45, "food": 0.40, "metals": 0.40,
        "logistics": 0.42, "transport": 0.56,
    }

    # Edge count per node for connectivity score (weight=0.20).
    edge_count: dict[str, int] = {}
    for e in supply_edges:
        for k in (e.get("src", ""), e.get("dst", "")):
            if k:
                edge_count[k] = edge_count.get(k, 0) + 1

    # Init node scores
    node_scores: dict[str, dict[str, float]] = {}
    for n in supply_nodes:
        nid = n.get("nodeId", "")
        dom = n.get("domain", "")
        cc = n.get("countryCode", "")
        bal_key = f"{dom}.{cc}"
        bal = balance_index.get(bal_key, {})

        # Seed pressure from balance + shock_seeds
        seed = shock_seeds.get(bal_key, 0.0)
        supply_t = float(n.get("supplyCapacity") or 1)
        demand_t = float(n.get("demandCapacity") or supply_t)
        imbalance = max(0, (demand_t - supply_t) / max(supply_t, 1)) if supply_t > 0 else 0

        # Confidence = freshness(30%) + reliability(25%) + connectivity(20%) + cargo_price(15%) + corroboration(10%)
        freshness = 0.70 if bal else 0.30
        reliability = _DOMAIN_RELIABILITY.get(dom, 0.40)
        n_edges = edge_count.get(nid, 0)
        connectivity = min(1.0, (n_edges / 10.0) ** 0.5)
        cargo_price = 1.0 if (float(bal.get("supplyQuantity") or 0) > 0 or float(bal.get("balanceQuantity") or 0) != 0) else 0.0
        corroboration = float(bal.get("confidence") or 0.5)
        confidence = round(
            0.30 * freshness
            + 0.25 * reliability
            + 0.20 * connectivity
            + 0.15 * cargo_price
            + 0.10 * corroboration,
            4,
        )

        node_scores[nid] = {
            "supply": min(1.0, max(imbalance, seed)),
            "demand": float(bal.get("demandQuantity", 0)) / max(float(bal.get("supplyQuantity", 1)), 1) if bal else 0,
            "price": 0.0,
            "downstream": 0.0,
            "structural": 0.0,
            "confidence": confidence,
        }

    prev_max_risk = 999.0
    stable_count = 0
    superstep = 0

    for superstep in range(max_iter):
        new_scores: dict[str, dict[str, float]] = {}
        max_delta = 0.0

        for nid, scores in node_scores.items():
            # Aggregate messages from upstream
            upstream_pressure = 0.0
            upstream_edges = upstream.get(nid, [])
            for e in upstream_edges:
                src = e.get("src", "")
                if src in node_scores:
                    src_risk = _compute_risk(node_scores[src])
                    w = float(e.get("dependencyWeight", 0.5))
                    conf = float(e.get("confidence", 0.5))
                    upstream_pressure += src_risk * w * conf

            if upstream_edges:
                upstream_pressure = min(1.0, upstream_pressure / len(upstream_edges))

            new = dict(scores)
            new["supply"] = min(1.0, scores.get("supply", 0) + upstream_pressure * 0.5)
            new["downstream"] = min(1.0, upstream_pressure)

            old_risk = _compute_risk(scores)
            new_risk = _compute_risk(new)
            max_delta = max(max_delta, abs(new_risk - old_risk))
            new_scores[nid] = new

        node_scores = new_scores

        if max_delta < 0.03:
            stable_count += 1
            if stable_count >= 2:
                break
        else:
            stable_count = 0
        prev_max_risk = max_delta

    # Aggregate to company exposure
    company_map: dict[str, list[dict[str, float]]] = {}
    node_by_id = {n.get("nodeId", ""): n for n in supply_nodes}
    for nid, scores in node_scores.items():
        n = node_by_id.get(nid, {})
        op = n.get("operatorDid", "")
        if not op:
            continue
        if op not in company_map:
            company_map[op] = []
        company_map[op].append({**scores, "risk": _compute_risk(scores)})

    company_exposures: list[dict[str, Any]] = []
    for op, node_list in company_map.items():
        avg_risk = sum(n["risk"] for n in node_list) / len(node_list)
        avg_conf = sum(n.get("confidence", 0.5) for n in node_list) / len(node_list)
        company_exposures.append({
            "companyDid": op,
            "riskScore": round(avg_risk, 4),
            "supplyPressure": round(sum(n.get("supply", 0) for n in node_list) / len(node_list), 4),
            "demandPressure": round(sum(n.get("demand", 0) for n in node_list) / len(node_list), 4),
            "pricePressure": round(sum(n.get("price", 0) for n in node_list) / len(node_list), 4),
            "downstreamPressure": round(sum(n.get("downstream", 0) for n in node_list) / len(node_list), 4),
            "structuralPressure": round(sum(n.get("structural", 0) for n in node_list) / len(node_list), 4),
            "confidence": round(avg_conf, 4),
            "nodeCount": len(node_list),
        })

    company_exposures.sort(key=lambda x: x["riskScore"], reverse=True)
    return {
        "node_scores": node_scores,
        "company_exposures": company_exposures,
        "superstep": superstep + 1,
        "converged": stable_count >= 2,
    }


def _compute_risk(scores: dict[str, float]) -> float:
    return (
        scores.get("supply", 0) * 0.30
        + scores.get("demand", 0) * 0.20
        + scores.get("price", 0) * 0.20
        + scores.get("downstream", 0) * 0.20
        + scores.get("structural", 0) * 0.10
    )


async def _node_write_signals(state: _State) -> dict[str, Any]:
    company_exposures = state.get("company_exposures") or []
    run_id = state.get("run_id", "")
    if not _RW_URL or not company_exposures:
        return {"signals_written": 0}

    signals_written = 0
    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            for ce in company_exposures:
                risk = float(ce.get("riskScore", 0))
                conf = float(ce.get("confidence", 0))
                if risk < 0.3:
                    continue
                severity = "critical" if risk >= 0.8 else "high" if risk >= 0.6 else "medium" if risk >= 0.4 else "low"
                signal_id = f"jukyu-signal:{time.strftime('%Y%m%d')}:{ce.get('companyDid','?')[:30]}:{run_id[-8:]}"
                vertex_id = f"at://jukyu001.etzhayyim.com/com.etzhayyim.apps.jukyu.notificationSignal/{uuid.uuid4().hex[:12]}"

                # Delete then insert (RW no ON CONFLICT)
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW(), CURRENT_DATE,
                            %s, 'anon')
                    """,
                    (
                        vertex_id, signal_id, ce.get("companyDid"), run_id,
                        risk, conf, severity, state.get("domain") or "global",
                        "Review supply chain exposure and assess procurement alternatives",
                        _APP_DID,
                    ),
                )

                # Also upsert company exposure record
                ce_vertex_id = f"at://jukyu001.etzhayyim.com/com.etzhayyim.apps.jukyu.companyExposure/{uuid.uuid4().hex[:12]}"
                await cur.execute(
                    "DELETE FROM vertex_jukyu_company_exposure WHERE company_did = %s AND run_id = %s",
                    (ce.get("companyDid"), run_id),
                )
                await cur.execute(
                    """
                    INSERT INTO vertex_jukyu_company_exposure
                        (vertex_id, exposure_id, company_did, run_id,
                         risk_score, confidence,
                         supply_pressure, demand_pressure, price_pressure,
                         downstream_pressure, structural_pressure, domain, created_date,
                         actor_did, org_did)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE,
                            %s, 'anon')
                    """,
                    (
                        ce_vertex_id, f"exp:{run_id[:20]}:{ce.get('companyDid','?')[:20]}",
                        ce.get("companyDid"), run_id,
                        risk, conf,
                        ce.get("supplyPressure", 0), ce.get("demandPressure", 0),
                        ce.get("pricePressure", 0), ce.get("downstreamPressure", 0),
                        ce.get("structuralPressure", 0), state.get("domain") or "global",
                        _APP_DID,
                    ),
                )
                signals_written += 1
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("write_signals failed")
        return {"signals_written": signals_written, "error": f"write_signals: {exc!s}"[:200]}

    return {"signals_written": signals_written}


async def _node_enrich_signals(state: _State) -> dict[str, Any]:
    """Optional LLM enrichment: generate title/body/action for top-N signals."""
    if not state.get("with_llm"):
        return {"signals_enriched": 0}

    company_exposures = (state.get("company_exposures") or [])[:_ENRICH_MAX]
    enriched = 0
    domain = state.get("domain") or "global"

    try:
        import httpx
        headers = {"Content-Type": "application/json"}
        if _LLM_API_KEY:
            headers["Authorization"] = f"Bearer {_LLM_API_KEY}"

        for ce in company_exposures:
            risk = float(ce.get("riskScore", 0))
            if risk < 0.4:
                continue
            prompt = (
                f"Write a brief executive signal for a supply-chain risk alert.\n"
                f"Company: {ce.get('companyDid','?')}\n"
                f"Domain: {domain}\n"
                f"Risk score: {risk:.2f} (supply={ce.get('supplyPressure',0):.2f}, "
                f"demand={ce.get('demandPressure',0):.2f})\n\n"
                f"Output JSON with fields: title (< 60 chars), body (< 200 chars), recommended_action (< 100 chars)."
            )
            payload = {
                "model": _NARRATIVE_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a supply-chain risk analyst. Output only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 256,
                "temperature": 0.3,
            }
            async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
                resp = await client.post(f"{_LLM_URL}/v1/chat/completions", json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            enriched += 1
    except Exception as exc:  # noqa: BLE001
        _log.warning("enrich_signals LLM call failed (non-fatal): %s", exc)

    return {"signals_enriched": enriched}


async def _node_read_outbox(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"outbox": []}
    run_id = state.get("run_id", "")
    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            await cur.execute(
                """
                SELECT signal_id, target_company_did, risk_score, confidence,
                       severity, domain, recommended_action, notification_status, emitted_at
                FROM vertex_jukyu_notification_signal
                WHERE run_id = %s
                ORDER BY risk_score DESC
                LIMIT 100
                """,
                (run_id,),
            )
            rows = await cur.fetchall()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.warning("read_outbox failed: %s", exc)
        return {"outbox": []}

    outbox = [
        {
            "signalId": r[0], "targetCompanyDid": r[1],
            "riskScore": float(r[2] or 0), "confidence": float(r[3] or 0),
            "severity": r[4], "domain": r[5],
            "recommendedAction": r[6], "notificationStatus": r[7],
            "emittedAt": str(r[8] or ""),
        }
        for r in rows
    ]
    return {"outbox": outbox}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.runStressPropagation",
        object_id=state.get("run_id", "unknown"),
        object_type="jukyu.pregelRun",
        attributes={
            "superstep": state.get("superstep", 0),
            "converged": state.get("converged", False),
            "signalsWritten": state.get("signals_written", 0),
            "companyCount": len(state.get("company_exposures") or []),
        },
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("init_run", _node_init_run)
    g.add_node("read_balance", _node_read_balance, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("read_chain", _node_read_chain, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("parse_scenario", _node_parse_scenario)
    g.add_node("propagate", _node_propagate)
    g.add_node("write_signals", _node_write_signals, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("enrich_signals", _node_enrich_signals)
    g.add_node("read_outbox", _node_read_outbox, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("audit", _node_audit)

    g.add_edge(START, "init_run")
    g.add_edge("init_run", "read_balance")
    g.add_edge("read_balance", "read_chain")
    g.add_edge("read_chain", "parse_scenario")
    g.add_edge("parse_scenario", "propagate")
    g.add_edge("propagate", "write_signals")
    g.add_edge("write_signals", "enrich_signals")
    g.add_edge("enrich_signals", "read_outbox")
    g.add_edge("read_outbox", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="run_stress_propagation")
