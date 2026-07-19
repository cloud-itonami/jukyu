"""Typed state schemas for jukyu LangGraph graphs."""

from __future__ import annotations

from typing import Any, TypedDict


class BalanceRow(TypedDict, total=False):
    domain: str
    country_code: str
    product_family: str
    supply_tonnes: float
    demand_tonnes: float
    inventory_tonnes: float
    balance: float
    price_usd_tonne: float
    confidence: float
    freshness_h: float
    observed_at: str


class SupplyNode(TypedDict, total=False):
    node_id: str
    node_type: str
    domain: str
    country_code: str
    operator_did: str
    capacity_tonnes_day: float
    risk_score: float
    confidence: float


class SupplyEdge(TypedDict, total=False):
    src: str
    dst: str
    edge_type: str
    commodity_code: str
    capacity_tonnes_day: float
    confidence: float


class CompanyExposure(TypedDict, total=False):
    company_did: str
    company_name: str
    domain: str
    country_code: str
    risk_score: float
    supply_pressure: float
    demand_pressure: float
    price_pressure: float
    downstream_pressure: float
    structural_pressure: float
    confidence: float
    affected_products: list[str]
    evidence_count: int
    notification_status: str


class PregelMessage(TypedDict, total=False):
    src: str
    dst: str
    edge_type: str
    commodity_code: str
    capacity_tonnes_day: float
    shock_type: str | None
    pressure_delta: float
    confidence: float
    evidence: list[dict[str, Any]]


class NotificationSignal(TypedDict, total=False):
    signal_id: str
    target_company_did: str
    domain: str
    product_family: str
    risk_score: float
    confidence: float
    severity: str
    affected_chain: list[str]
    evidence: list[dict[str, Any]]
    recommended_action: str
    title: str | None
    body: str | None
    created_at: str


class ShockEvent(TypedDict, total=False):
    shock_type: str
    domain: str
    country_code: str
    severity: float
    duration_days: int
    description: str
    source_url: str | None


class EquilibriumState(TypedDict, total=False):
    run_id: str
    domain: str
    with_llm: bool
    scenario_text: str | None
    shock_seeds: dict[str, float]
    max_iterations: int
    balance_rows: list[dict[str, Any]]
    supply_nodes: list[dict[str, Any]]
    supply_edges: list[dict[str, Any]]
    shocks: list[dict[str, Any]]
    pregel_messages: list[dict[str, Any]]
    company_exposures: list[dict[str, Any]]
    signals_written: int
    signals_enriched: int
    outbox: list[dict[str, Any]]
    superstep: int
    converged: bool
    error: str | None
    latency_ms: int
