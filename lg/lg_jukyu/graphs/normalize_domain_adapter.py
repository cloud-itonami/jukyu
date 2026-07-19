"""jukyu `normalizeDomainAdapter` graph — normalize one domain's source tables into
vertex_jukyu_* and edge_jukyu_* tables.

NSID: com.etzhayyim.apps.jukyu.normalizeDomainAdapter
Endpoint: POST /cron/domain-adapter/{domain}

Supported domains and their source tables (per CLAUDE.md):
  naphtha     : mv_naphtha_country_balance, mv_naphtha_cargo_flow,
                mv_naphtha_price_latest, mv_naphtha_supply_chain_trace
  crude_oil   : vertex_oil_field, vertex_oil_terminal, vertex_refinery
  energy      : vertex_energy
  food        : vertex_agriculture
  metals      : vertex_manufacturing (metal/mining categories)
  logistics   : vertex_logistics
  transport   : multi-domain cargo legs (includes semiconductor legs)

Note: semiconductor is NOT a standalone cron-triggered adapter — it is processed
as part of the transport domain pass.
"""

from __future__ import annotations

import hashlib
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


def _supply_node_vid(node_code: str, domain: str) -> str:
    """Deterministic AT URI for a supply node, stable across runs."""
    h = hashlib.sha256(f"{node_code}:{domain}".encode()).hexdigest()[:16]
    return f"at://jukyu001.etzhayyim.com/com.etzhayyim.apps.jukyu.supplyNode/{h}"

# Domain confidence scores from CLAUDE.md (semiconductor handled within transport)
_DOMAIN_CONFIDENCE: dict[str, float] = {
    "naphtha": 0.72,
    "crude_oil": 0.60,
    "energy": 0.45,
    "food": 0.40,
    "metals": 0.40,
    "logistics": 0.42,
    "transport": 0.56,
}


class _State(TypedDict, total=False):
    domain: str
    source_actor: str | None
    target_contract: str | None
    upserted_nodes: int
    upserted_edges: int
    upserted_balances: int
    freshness_at: str
    error: str | None


async def _node_normalize(state: _State) -> dict[str, Any]:
    domain = (state.get("domain") or "").strip().lower()
    if not domain:
        return {"error": "domain is required"}
    if not _RW_URL:
        return {"error": "RW_URL not set", "upserted_nodes": 0}

    confidence = _DOMAIN_CONFIDENCE.get(domain, 0.40)

    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            if domain == "naphtha":
                result = await _normalize_naphtha(cur, confidence)
            elif domain == "crude_oil":
                result = await _normalize_crude_oil(cur, confidence)
            elif domain == "semiconductor":
                result = await _normalize_semiconductor(cur, confidence)
            elif domain in ("energy", "food", "metals", "logistics"):
                result = await _normalize_generic(cur, domain, confidence)
            elif domain == "transport":
                result = await _normalize_transport(cur, confidence)
            else:
                result = {"upserted_nodes": 0, "upserted_edges": 0, "upserted_balances": 0,
                          "error": f"unsupported domain: {domain}"}
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("normalizeDomainAdapter failed for %s", domain)
        return {"error": f"{domain}: {exc!s}"[:300], "upserted_nodes": 0}

    return {**result, "freshness_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


async def _upsert_supply_node(
    cur: Any,
    node_code: str,
    node_kind: str,
    domain: str,
    country_code: str,
    operator_did: str,
    supply_capacity: float,
    demand_capacity: float = 0.0,
) -> None:
    vertex_id = _supply_node_vid(node_code, domain)
    await cur.execute(
        "DELETE FROM vertex_jukyu_supply_node WHERE node_code = %s AND domain = %s",
        (node_code, domain),
    )
    await cur.execute(
        """
        INSERT INTO vertex_jukyu_supply_node
            (vertex_id, node_code, node_kind, domain, country_code,
             operator_did, supply_capacity, demand_capacity,
             source_table, created_date, actor_did, org_did)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, %s, 'anon')
        """,
        (vertex_id, node_code, node_kind, domain, country_code,
         operator_did, supply_capacity, demand_capacity, domain, _APP_DID),
    )


async def _normalize_naphtha(cur: Any, confidence: float) -> dict[str, Any]:
    nodes = edges = balances = 0

    # Read supply chain trace
    try:
        await cur.execute(
            """
            SELECT node_id, node_type, country_code, operator_did,
                   capacity_tonnes_day, supply_tonnes, demand_tonnes
            FROM mv_naphtha_supply_chain_trace
            LIMIT 5000
            """
        )
        rows = await cur.fetchall()
    except Exception:
        rows = []

    for r in rows:
        try:
            await _upsert_supply_node(
                cur, r[0], r[1], "naphtha", r[2] or "XX",
                r[3] or "", float(r[4] or 0), float(r[5] or 0),
            )
            nodes += 1
        except Exception as exc:  # noqa: BLE001
            _log.debug("naphtha node upsert skip: %s", exc)

    # Read country balance
    try:
        await cur.execute(
            """
            SELECT country_code, product_family,
                   supply_quantity, demand_quantity, inventory_quantity,
                   price_usd_unit, observed_at
            FROM mv_naphtha_country_balance
            LIMIT 2000
            """
        )
        bal_rows = await cur.fetchall()
    except Exception:
        bal_rows = []

    for r in bal_rows:
        try:
            obs_id = f"naphtha-balance:{r[0]}:{r[1]}"
            vertex_id = f"at://jukyu001.etzhayyim.com/com.etzhayyim.apps.jukyu.balanceObservation/{uuid.uuid4().hex[:12]}"
            await cur.execute(
                """
                INSERT INTO vertex_jukyu_balance_observation
                    (vertex_id, observation_id, domain, country_code, product_family,
                     supply_quantity, demand_quantity, inventory_quantity,
                     price_usd_unit, confidence, observed_at, created_date,
                     actor_did, org_did)
                VALUES (%s, %s, 'naphtha', %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE,
                        %s, 'anon')
                """,
                (vertex_id, obs_id,
                 r[0], r[1], float(r[2] or 0), float(r[3] or 0),
                 float(r[4] or 0), float(r[5] or 0), confidence, str(r[6] or ""),
                 _APP_DID),
            )
            balances += 1
        except Exception as exc:  # noqa: BLE001
            _log.debug("naphtha balance upsert skip: %s", exc)

    return {"upserted_nodes": nodes, "upserted_edges": edges, "upserted_balances": balances}


async def _normalize_crude_oil(cur: Any, confidence: float) -> dict[str, Any]:
    nodes = edges = balances = 0
    for table, node_type in [
        ("vertex_oil_field", "field"),
        ("vertex_oil_terminal", "terminal"),
        ("vertex_refinery", "refinery"),
    ]:
        try:
            await cur.execute(
                f"SELECT vertex_id, country_code, operator_did, capacity FROM {table} LIMIT 2000"
            )
            rows = await cur.fetchall()
        except Exception:
            continue
        for r in rows:
            try:
                nid = f"crude_oil-{node_type}:{r[0]}"
                await _upsert_supply_node(
                    cur, nid, node_type, "crude_oil", r[1] or "XX",
                    r[2] or "", float(r[3] or 0),
                )
                nodes += 1
            except Exception:
                pass
    return {"upserted_nodes": nodes, "upserted_edges": edges, "upserted_balances": balances}


async def _normalize_semiconductor(cur: Any, confidence: float) -> dict[str, Any]:
    nodes = edges = balances = 0
    for table, node_type in [
        ("vertex_open_smartphone_ems_facility", "ems_facility"),
        ("vertex_open_smartphone_soc_design", "soc_design"),
    ]:
        try:
            await cur.execute(
                f"SELECT vertex_id, country_code, operator_did FROM {table} LIMIT 2000"
            )
            rows = await cur.fetchall()
        except Exception:
            continue
        for r in rows:
            try:
                nid = f"semiconductor-{node_type}:{r[0]}"
                await _upsert_supply_node(
                    cur, nid, node_type, "semiconductor", r[1] or "XX",
                    r[2] or "", 0.0,
                )
                nodes += 1
            except Exception:
                pass
    return {"upserted_nodes": nodes, "upserted_edges": edges, "upserted_balances": balances}


async def _normalize_generic(cur: Any, domain: str, confidence: float) -> dict[str, Any]:
    table_map = {
        "energy": "vertex_energy",
        "food": "vertex_agriculture",
        "metals": "vertex_manufacturing",
        "logistics": "vertex_logistics",
    }
    table = table_map.get(domain, "")
    nodes = edges = balances = 0
    if not table:
        return {"upserted_nodes": 0, "upserted_edges": 0, "upserted_balances": 0}
    try:
        await cur.execute(
            f"SELECT vertex_id, category, code FROM {table} LIMIT 5000"
        )
        rows = await cur.fetchall()
    except Exception:
        return {"upserted_nodes": 0, "upserted_edges": 0, "upserted_balances": 0}

    for r in rows:
        try:
            nid = f"{domain}:{r[0]}"
            await _upsert_supply_node(
                cur, nid, r[1] or domain, domain, "XX", "", 0.0,
            )
            nodes += 1
        except Exception:
            pass
    return {"upserted_nodes": nodes, "upserted_edges": edges, "upserted_balances": balances}


async def _normalize_transport(cur: Any, confidence: float) -> dict[str, Any]:
    """Normalize cargo legs from vertex_jukyu_transport_leg into supply chain nodes and edges.

    Reads active/scheduled transport legs (crude_oil / naphtha / semiconductor domains)
    and projects each unique LOCODE port into vertex_jukyu_supply_node, then records
    per-product-family in-transit quantities as balance observations.
    """
    nodes = edges = balances = 0

    try:
        await cur.execute(
            """
            SELECT leg_id, domain, origin_locode, destination_locode,
                   carrier_did, operator_did, product_family,
                   quantity, quantity_unit, transport_mode, status,
                   route_risk_score, confidence
            FROM vertex_jukyu_transport_leg
            WHERE status IN ('en_route', 'scheduled', 'loading', 'discharging')
            LIMIT 10000
            """
        )
        legs = await cur.fetchall()
    except Exception:
        legs = []

    seen_ports: set[tuple[str, str]] = set()
    in_transit: dict[tuple[str, str, str], float] = {}  # (domain, product_family, dest) → qty

    for row in legs:
        (leg_id, domain, origin_locode, dest_locode, carrier_did, operator_did,
         product_family, quantity, quantity_unit, transport_mode, status,
         route_risk_score, leg_confidence) = row

        if not origin_locode or not dest_locode:
            continue
        domain = (domain or "transport").strip()
        origin_cc = origin_locode[:2] if len(origin_locode or "") >= 2 else "XX"
        dest_cc = dest_locode[:2] if len(dest_locode or "") >= 2 else "XX"
        qty = float(quantity or 0)
        leg_conf = float(leg_confidence or confidence)

        # Upsert origin port as a supply node.
        origin_key = (origin_locode, domain)
        if origin_key not in seen_ports:
            try:
                await _upsert_supply_node(
                    cur,
                    f"port:{origin_locode}",
                    "port",
                    domain,
                    origin_cc,
                    operator_did or carrier_did or "",
                    qty,
                    0.0,
                )
                nodes += 1
                seen_ports.add(origin_key)
            except Exception as exc:
                _log.debug("transport origin node skip %s: %s", origin_locode, exc)

        # Upsert destination port as a demand node.
        dest_key = (dest_locode, domain)
        if dest_key not in seen_ports:
            try:
                await _upsert_supply_node(
                    cur,
                    f"port:{dest_locode}",
                    "port",
                    domain,
                    dest_cc,
                    operator_did or carrier_did or "",
                    0.0,
                    qty,
                )
                nodes += 1
                seen_ports.add(dest_key)
            except Exception as exc:
                _log.debug("transport dest node skip %s: %s", dest_locode, exc)

        # Accumulate in-transit quantity per (domain, product_family, destination).
        key = (domain, product_family or "unknown", dest_locode)
        in_transit[key] = in_transit.get(key, 0.0) + qty

        # Record each leg as a supply dependency edge.
        try:
            edge_id = f"transport-leg:{leg_id or uuid.uuid4().hex[:12]}"
            await cur.execute(
                "DELETE FROM edge_jukyu_supply_dependency WHERE edge_id = %s",
                (edge_id,),
            )
            await cur.execute(
                """
                INSERT INTO edge_jukyu_supply_dependency
                    (edge_id, src_vid, dst_vid, domain, relationship,
                     product_family, capacity_quantity, quantity_unit,
                     confidence, status, created_date,
                     actor_did, org_did)
                VALUES (%s, %s, %s, %s, 'transport_cargo', %s, %s, %s, %s,
                        'active', CURRENT_DATE, %s, 'anon')
                """,
                (
                    edge_id,
                    _supply_node_vid(f"port:{origin_locode}", domain),
                    _supply_node_vid(f"port:{dest_locode}", domain),
                    domain,
                    product_family or "unknown",
                    qty,
                    quantity_unit or "kt/year",
                    leg_conf,
                    _APP_DID,
                ),
            )
            edges += 1
        except Exception as exc:
            _log.debug("transport edge skip %s: %s", leg_id, exc)

    # Record in-transit aggregate as balance observations.
    for (domain, product_family, dest_locode), total_qty in in_transit.items():
        try:
            obs_id = f"transport-intransit:{domain}:{product_family}:{dest_locode}"
            vertex_id = f"at://jukyu001.etzhayyim.com/com.etzhayyim.apps.jukyu.balanceObservation/{uuid.uuid4().hex[:12]}"
            dest_cc = dest_locode[:2] if len(dest_locode) >= 2 else "XX"
            await cur.execute(
                """
                INSERT INTO vertex_jukyu_balance_observation
                    (vertex_id, observation_id, domain, country_code, product_family,
                     supply_quantity, demand_quantity, inventory_quantity,
                     price_usd_unit, confidence, observed_at, created_date,
                     actor_did, org_did)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), CURRENT_DATE,
                        %s, 'anon')
                """,
                (vertex_id, obs_id, domain, dest_cc, product_family,
                 0.0, total_qty, total_qty, 0.0, confidence, _APP_DID),
            )
            balances += 1
        except Exception as exc:
            _log.debug("transport balance obs skip: %s", exc)

    return {"upserted_nodes": nodes, "upserted_edges": edges, "upserted_balances": balances}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.normalizeDomainAdapter",
        object_id=f"normalize:{state.get('domain','?')}:{int(time.time())}",
        object_type="jukyu.domainAdapter",
        attributes={
            "domain": state.get("domain"),
            "upsertedNodes": state.get("upserted_nodes", 0),
            "upsertedEdges": state.get("upserted_edges", 0),
            "upsertedBalances": state.get("upserted_balances", 0),
        },
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("normalize", _node_normalize, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("audit", _node_audit)
    g.add_edge(START, "normalize")
    g.add_edge("normalize", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="normalize_domain_adapter")
