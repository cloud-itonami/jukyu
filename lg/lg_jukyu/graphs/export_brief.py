"""jukyu `exportBrief` graph — LLM executive brief from latest outbox.

Model: gemma-4-e4b-it
Endpoint: POST /export/brief and NSID com.etzhayyim.apps.jukyu.exportBrief
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
_LLM_URL = os.environ.get("JUKYU_LLM_URL", "http://llm.etzhayyim.com")
_LLM_API_KEY = os.environ.get("JUKYU_LLM_API_KEY", "")
_NARRATIVE_MODEL = os.environ.get("JUKYU_LLM_NARRATIVE_MODEL", "gemma-4-e4b-it")
_LLM_TIMEOUT = float(os.environ.get("JUKYU_LLM_TIMEOUT", "30"))


class _State(TypedDict, total=False):
    domain: str | None
    limit: int
    outbox: list[dict[str, Any]]
    brief: str
    signal_count: int
    error: str | None


async def _node_read_outbox(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"outbox": [], "signal_count": 0}
    limit = max(1, min(50, int(state.get("limit") or 20)))
    domain = state.get("domain")

    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            params: list[Any] = []
            where = "WHERE notification_status IN ('pending', 'retry')"
            if domain:
                where += " AND domain = %s"
                params.append(domain)
            await cur.execute(
                f"""
                SELECT signal_id, target_company_did, risk_score, confidence,
                       severity, domain, recommended_action, title
                FROM mv_jukyu_notification_outbox
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
        _log.exception("export_brief read_outbox failed")
        return {"outbox": [], "signal_count": 0, "error": f"read: {exc!s}"[:200]}

    outbox = [
        {
            "signalId": r[0], "companyDid": r[1],
            "riskScore": float(r[2] or 0), "confidence": float(r[3] or 0),
            "severity": r[4], "domain": r[5],
            "recommendedAction": r[6], "title": r[7],
        }
        for r in rows
    ]
    return {"outbox": outbox, "signal_count": len(outbox)}


async def _node_generate_brief(state: _State) -> dict[str, Any]:
    outbox = state.get("outbox") or []
    if not outbox:
        return {"brief": "No pending signals in outbox."}

    domain = state.get("domain") or "global"
    signals_text = "\n".join(
        f"- [{s['severity'].upper()}] {s.get('companyDid','?')} "
        f"(risk={s['riskScore']:.2f}, conf={s['confidence']:.2f}): "
        f"{s.get('recommendedAction','')}"
        for s in outbox[:20]
    )

    prompt = (
        f"Write a 3-paragraph executive brief about the following supply-chain risk signals "
        f"for domain: {domain}.\n\n"
        f"Signals:\n{signals_text}\n\n"
        f"Format: (1) Situation overview (2) Top companies at risk with key facts "
        f"(3) Recommended actions. Be concise and precise."
    )

    try:
        import httpx
        headers = {"Content-Type": "application/json"}
        if _LLM_API_KEY:
            headers["Authorization"] = f"Bearer {_LLM_API_KEY}"
        payload = {
            "model": _NARRATIVE_MODEL,
            "messages": [
                {"role": "system", "content": "You are a senior commodity risk analyst writing executive briefs."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1024,
            "temperature": 0.5,
        }
        async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
            resp = await client.post(f"{_LLM_URL}/v1/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        brief = data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        _log.exception("export_brief LLM call failed")
        brief = f"Brief generation failed: {exc!s}"[:300]

    return {"brief": brief}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.exportBrief",
        object_id=f"brief:{int(time.time())}",
        object_type="jukyu.brief",
        attributes={"signalCount": state.get("signal_count", 0), "domain": state.get("domain")},
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("read_outbox", _node_read_outbox, retry_policy=RetryPolicy(max_attempts=3))
    g.add_node("generate_brief", _node_generate_brief)
    g.add_node("audit", _node_audit)
    g.add_edge(START, "read_outbox")
    g.add_edge("read_outbox", "generate_brief")
    g.add_edge("generate_brief", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="export_brief")
