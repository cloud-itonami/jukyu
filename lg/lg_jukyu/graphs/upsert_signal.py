"""jukyu `upsertSignal` graph — write notification signal to outbox.

NSID: com.etzhayyim.apps.jukyu.upsertSignal
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


class _State(TypedDict, total=False):
    signal_id: str
    target_company_did: str
    domain: str | None
    product_family: str | None
    risk_score: float
    confidence: float
    severity: str
    recommended_action: str | None
    title: str | None
    body: str | None
    ok: bool
    error: str | None


async def _node_write(state: _State) -> dict[str, Any]:
    company_did = state.get("target_company_did", "").strip()
    if not company_did:
        return {"ok": False, "error": "target_company_did is required"}
    if not _RW_URL:
        return {"ok": False, "error": "RW_URL not set"}

    signal_id = state.get("signal_id") or (
        f"jukyu-signal:{time.strftime('%Y%m%d')}:{company_did[:30]}:{uuid.uuid4().hex[:8]}"
    )
    vertex_id = f"at://jukyu001.etzhayyim.com/com.etzhayyim.apps.jukyu.notificationSignal/{uuid.uuid4().hex[:12]}"
    risk = float(state.get("risk_score") or 0)
    conf = float(state.get("confidence") or 0)
    severity = state.get("severity") or (
        "critical" if risk >= 0.8 else "high" if risk >= 0.6 else "medium" if risk >= 0.4 else "low"
    )

    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            await cur.execute(
                "DELETE FROM vertex_jukyu_notification_signal WHERE signal_id = %s",
                (signal_id,),
            )
            await cur.execute(
                """
                INSERT INTO vertex_jukyu_notification_signal
                    (vertex_id, signal_id, target_company_did, run_id,
                     risk_score, confidence, severity, domain,
                     recommended_action, title, body,
                     notification_status, emitted_at, created_date,
                     actor_did, org_did)
                VALUES (%s, %s, %s, 'manual', %s, %s, %s, %s, %s, %s, %s,
                        'pending', NOW(), CURRENT_DATE, %s, 'anon')
                """,
                (
                    vertex_id, signal_id, company_did,
                    risk, conf, severity,
                    state.get("domain") or "global",
                    state.get("recommended_action") or "",
                    state.get("title"), state.get("body"),
                    _APP_DID,
                ),
            )
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        _log.exception("upsertSignal write failed")
        return {"ok": False, "error": f"write: {exc!s}"[:300]}

    return {"ok": True, "signal_id": signal_id}


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.upsertSignal",
        object_id=state.get("signal_id", "unknown"),
        object_type="jukyu.notificationSignal",
        attributes={"ok": state.get("ok", False), "companyDid": state.get("target_company_did")},
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("write", _node_write, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("audit", _node_audit)
    g.add_edge(START, "write")
    g.add_edge("write", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="upsert_signal")
