"""jukyu `extractShocks` graph — news text → structured shock events.

Model: qwen3-30b
Endpoint: POST /extract/shocks and NSID com.etzhayyim.apps.jukyu.extractShocks
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from lg_jukyu.audit import emit_audit_bg

_log = logging.getLogger(__name__)

_APP_DID = os.environ.get("JUKYU_APP_DID", "did:web:jukyu.etzhayyim.com")
_LLM_URL = os.environ.get("JUKYU_LLM_URL", "http://llm.etzhayyim.com")
_LLM_API_KEY = os.environ.get("JUKYU_LLM_API_KEY", "")
_EXTRACTION_MODEL = os.environ.get("JUKYU_LLM_EXTRACTION_MODEL", "qwen3-30b")
_LLM_TIMEOUT = float(os.environ.get("JUKYU_LLM_TIMEOUT", "30"))

_SYSTEM_PROMPT = """You are a commodity supply-chain analyst.
Extract supply-demand shock events from the provided news text.
Return a valid JSON array. Each item must have these fields:
  shock_type: string (one of: cargo_delay, port_closure, plant_outage, war_risk,
               price_spike, demand_surge, inventory_drawdown, sanctions, weather, other)
  domain: string (one of: naphtha, crude_oil, semiconductor, energy, food, metals, logistics, transport, unknown)
  country_code: string (ISO-3166-1 alpha-2 or XX if unknown)
  severity: float (0.0 to 1.0)
  duration_days: integer (estimated disruption days; 0 if unknown)
  description: string (one sentence summary)
  source_url: string or null

Output ONLY the JSON array, no other text."""


class _State(TypedDict, total=False):
    text: str
    source_url: str | None
    shocks: list[dict[str, Any]]
    shock_count: int
    error: str | None


async def _node_extract(state: _State) -> dict[str, Any]:
    text = (state.get("text") or "").strip()
    if not text:
        return {"shocks": [], "shock_count": 0, "error": "text is required"}

    try:
        import httpx
        headers = {"Content-Type": "application/json"}
        if _LLM_API_KEY:
            headers["Authorization"] = f"Bearer {_LLM_API_KEY}"
        payload = {
            "model": _EXTRACTION_MODEL,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"News text:\n\n{text[:4000]}"},
            ],
            "max_tokens": 2048,
            "temperature": 0.1,
        }
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
            resp = await client.post(f"{_LLM_URL}/v1/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON array from response
        match = re.search(r"\[.*\]", content, re.DOTALL)
        shocks: list[dict[str, Any]] = json.loads(match.group()) if match else []

        # Validate and clean
        cleaned = []
        for s in shocks:
            if isinstance(s, dict):
                cleaned.append({
                    "shockType": str(s.get("shock_type", "other")),
                    "domain": str(s.get("domain", "unknown")),
                    "countryCode": str(s.get("country_code", "XX"))[:2].upper(),
                    "severity": min(1.0, max(0.0, float(s.get("severity", 0.5)))),
                    "durationDays": max(0, int(s.get("duration_days", 0))),
                    "description": str(s.get("description", ""))[:300],
                    "sourceUrl": s.get("source_url") or state.get("source_url"),
                })
        return {"shocks": cleaned, "shock_count": len(cleaned)}
    except Exception as exc:  # noqa: BLE001
        _log.exception("extractShocks LLM call failed")
        return {"shocks": [], "shock_count": 0, "error": f"extract: {exc!s}"[:300]}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.extractShocks",
        object_id=f"shocks:{int(time.time())}",
        object_type="jukyu.shockEvent",
        attributes={"shockCount": state.get("shock_count", 0)},
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("extract", _node_extract)
    g.add_node("audit", _node_audit)
    g.add_edge(START, "extract")
    g.add_edge("extract", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="extract_shocks")
