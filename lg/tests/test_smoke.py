"""Smoke tests for lg-jukyu (mirrors lg-yukkuri test pattern).

Tests compile correctness, server structure, NSID map, graph existence,
and cron config — no DB or LLM required.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

LG_ROOT = Path(__file__).parent.parent
LANGGRAPH_JSON = LG_ROOT / "langgraph.json"


# ── Compile tests ────────────────────────────────────────────────────────

def test_server_imports():
    mod = importlib.import_module("lg_jukyu.server")
    assert hasattr(mod, "app"), "app FastAPI instance missing"
    assert hasattr(mod, "GRAPHS"), "GRAPHS dict missing"
    assert hasattr(mod, "_NSID_TO_ASSISTANT"), "_NSID_TO_ASSISTANT missing"


def test_state_imports():
    mod = importlib.import_module("lg_jukyu.state")
    assert hasattr(mod, "EquilibriumState")
    assert hasattr(mod, "NotificationSignal")
    assert hasattr(mod, "CompanyExposure")


def test_checkpointer_imports():
    mod = importlib.import_module("lg_jukyu.checkpointer")
    assert hasattr(mod, "build_checkpointer")


def test_cron_imports():
    mod = importlib.import_module("lg_jukyu.cron")
    assert hasattr(mod, "start_cron")
    assert hasattr(mod, "stop_cron")


def test_audit_imports():
    mod = importlib.import_module("lg_jukyu.audit")
    assert hasattr(mod, "emit_audit_bg")
    assert hasattr(mod, "emit_audit")


# ── Graph compile tests ──────────────────────────────────────────────────

GRAPH_MODULES = [
    "lg_jukyu.graphs.health",
    "lg_jukyu.graphs.query_balance",
    "lg_jukyu.graphs.query_supply_chain",
    "lg_jukyu.graphs.rank_company_exposure",
    "lg_jukyu.graphs.explain_node",
    "lg_jukyu.graphs.run_stress_propagation",
    "lg_jukyu.graphs.upsert_signal",
    "lg_jukyu.graphs.export_brief",
    "lg_jukyu.graphs.notify_company",
    "lg_jukyu.graphs.normalize_domain_adapter",
    "lg_jukyu.graphs.extract_shocks",
    "lg_jukyu.graphs.equilibrium",
]


@pytest.mark.parametrize("module_path", GRAPH_MODULES)
def test_graph_compiles(module_path: str):
    mod = importlib.import_module(module_path)
    assert hasattr(mod, "GRAPH"), f"{module_path} missing GRAPH export"
    graph = mod.GRAPH
    assert graph is not None


# ── NSID map completeness test ───────────────────────────────────────────

EXPECTED_NSIDS = {
    "com.etzhayyim.apps.jukyu.health",
    "com.etzhayyim.apps.jukyu.queryBalance",
    "com.etzhayyim.apps.jukyu.querySupplyChain",
    "com.etzhayyim.apps.jukyu.rankCompanyExposure",
    "com.etzhayyim.apps.jukyu.explainNode",
    "com.etzhayyim.apps.jukyu.runStressPropagation",
    "com.etzhayyim.apps.jukyu.upsertSignal",
    "com.etzhayyim.apps.jukyu.exportBrief",
    "com.etzhayyim.apps.jukyu.notifyCompany",
    "com.etzhayyim.apps.jukyu.normalizeDomainAdapter",
    "com.etzhayyim.apps.jukyu.extractShocks",
}


def test_nsid_map_coverage():
    mod = importlib.import_module("lg_jukyu.server")
    nsid_map: dict = mod._NSID_TO_ASSISTANT
    missing = EXPECTED_NSIDS - set(nsid_map.keys())
    assert not missing, f"NSIDs missing from _NSID_TO_ASSISTANT: {missing}"


def test_nsid_map_all_graphs_exist():
    mod = importlib.import_module("lg_jukyu.server")
    nsid_map: dict = mod._NSID_TO_ASSISTANT
    graphs: dict = mod.GRAPHS
    for nsid, assistant_id in nsid_map.items():
        assert assistant_id in graphs, f"NSID {nsid} → assistant {assistant_id} not in GRAPHS"


# ── GRAPHS dict completeness ─────────────────────────────────────────────

EXPECTED_GRAPHS = {
    "health", "query_balance", "query_supply_chain", "rank_company_exposure",
    "explain_node", "run_stress_propagation", "upsert_signal", "export_brief",
    "notify_company", "normalize_domain_adapter", "extract_shocks", "equilibrium",
}


def test_graphs_dict_completeness():
    mod = importlib.import_module("lg_jukyu.server")
    graphs: dict = mod.GRAPHS
    missing = EXPECTED_GRAPHS - set(graphs.keys())
    assert not missing, f"Missing graphs in GRAPHS dict: {missing}"


# ── langgraph.json tests ─────────────────────────────────────────────────

def test_langgraph_json_exists():
    assert LANGGRAPH_JSON.exists(), "langgraph.json not found"


def test_langgraph_json_graphs():
    cfg = json.loads(LANGGRAPH_JSON.read_text())
    graphs = cfg.get("graphs", {})
    missing = EXPECTED_GRAPHS - set(graphs.keys())
    assert not missing, f"langgraph.json missing graphs: {missing}"


def test_langgraph_json_crons():
    cfg = json.loads(LANGGRAPH_JSON.read_text())
    crons = cfg.get("crons", [])
    assert len(crons) >= 1, "no crons defined in langgraph.json"
    # At minimum the 15-min equilibrium loop must be there
    equil_crons = [c for c in crons if c.get("graph") == "equilibrium"]
    assert equil_crons, "equilibrium cron missing in langgraph.json"
    assert equil_crons[0].get("schedule") == "*/15 * * * *"


def test_langgraph_json_domain_adapters_scheduled():
    cfg = json.loads(LANGGRAPH_JSON.read_text())
    crons = cfg.get("crons", [])
    adapter_crons = [c for c in crons if c.get("graph") == "normalize_domain_adapter"]
    domains = {c.get("input", {}).get("domain") for c in adapter_crons}
    expected_domains = {"naphtha", "crude_oil", "energy", "food", "metals", "logistics", "transport"}
    missing = expected_domains - domains
    assert not missing, f"domain adapters not scheduled: {missing}"


# ── camelCase conversion test ─────────────────────────────────────────────

def test_camel_to_snake():
    mod = importlib.import_module("lg_jukyu.server")
    fn = mod._camel_to_snake
    assert fn("countryCode") == "country_code"
    assert fn("riskScore") == "risk_score"
    assert fn("productFamily") == "product_family"
    assert fn("withLLM") == "with_l_l_m" or fn("withLLM") == "with_llm"  # implementation detail
    assert fn("nodeCode") == "node_code"
    assert fn("targetCompanyDid") == "target_company_did"
