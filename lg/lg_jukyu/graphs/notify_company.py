"""jukyu `notifyCompany` graph — dispatch signal to target company actor.

NSID: com.etzhayyim.apps.jukyu.notifyCompany
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
_BPMN_URL = os.environ.get(
    "BPMN_DISPATCHER_INTERNAL_URL",
    "http://bpmn-dispatcher.mitama-udf.svc.cluster.local:8080",
).rstrip("/")
_INTERNAL_SECRET = os.environ.get("BPMN_DISPATCHER_INTERNAL_SECRET", "")


class _State(TypedDict, total=False):
    signal_id: str
    target_company_did: str
    channel: str  # mcp | email | webhook
    delivery_mode: str  # route_to_company_actor | direct
    ok: bool
    delivery_status: str
    trace_id: str
    error: str | None


async def _node_load_signal(state: _State) -> dict[str, Any]:
    signal_id = state.get("signal_id", "").strip()
    if not signal_id:
        return {"ok": False, "error": "signal_id is required"}
    if not _RW_URL:
        return {"ok": False, "error": "RW_URL not set"}

    try:
        import psycopg
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
        try:
            cur = conn.cursor()
            await cur.execute(
                """
                SELECT signal_id, target_company_did, risk_score, confidence,
                       severity, domain, recommended_action, title, body
                FROM vertex_jukyu_notification_signal
                WHERE signal_id = %s
                LIMIT 1
                """,
                (signal_id,),
            )
            row = await cur.fetchone()
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"load: {exc!s}"[:200]}

    if not row:
        return {"ok": False, "error": f"signal not found: {signal_id}"}

    return {
        "signal_id": row[0],
        "target_company_did": row[1] or state.get("target_company_did", ""),
        "_loaded_signal": {
            "riskScore": float(row[2] or 0), "confidence": float(row[3] or 0),
            "severity": row[4], "domain": row[5],
            "recommendedAction": row[6], "title": row[7], "body": row[8],
        },
    }


async def _node_dispatch(state: _State) -> dict[str, Any]:
    signal_id = state.get("signal_id", "")
    company_did = state.get("target_company_did", "")
    channel = state.get("channel") or "mcp"
    trace_id = f"jukyu-notify:{signal_id[:20]}:{int(time.time())}"

    try:
        import httpx
        headers = {"Content-Type": "application/json"}
        if _INTERNAL_SECRET:
            headers["x-internal-trust"] = _INTERNAL_SECRET

        payload = {
            "actor": _APP_DID,
            "activity": "jukyu.notifyCompany",
            "objectId": signal_id,
            "objectType": "jukyu.notificationSignal",
            "attributes": {
                "targetCompanyDid": company_did,
                "channel": channel,
                "traceId": trace_id,
                "signal": state.get("_loaded_signal") or {},
            },
        }
        url = f"{_BPMN_URL}/xrpc/com.etzhayyim.generic.audit.emit"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            dispatch_ok = resp.status_code < 400
    except Exception as exc:  # noqa: BLE001
        _log.warning("notify_company dispatch failed (non-fatal): %s", exc)
        dispatch_ok = False

    # Update delivery status in DB
    if _RW_URL:
        try:
            import psycopg
            conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True)
            try:
                cur = conn.cursor()
                new_status = "dispatched" if dispatch_ok else "dispatch_failed"
                await cur.execute(
                    """
                    UPDATE vertex_jukyu_notification_signal
                    SET notification_status = %s
                    WHERE signal_id = %s
                    """,
                    (new_status, signal_id),
                )
            finally:
                await conn.close()
        except Exception as exc:  # noqa: BLE001
            _log.warning("notify_company status update failed: %s", exc)

    return {
        "ok": dispatch_ok,
        "delivery_status": "dispatched" if dispatch_ok else "dispatch_failed",
        "trace_id": trace_id,
    }


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.notifyCompany",
        object_id=state.get("signal_id", "unknown"),
        object_type="jukyu.notificationSignal",
        attributes={
            "ok": state.get("ok", False),
            "traceId": state.get("trace_id"),
            "companyDid": state.get("target_company_did"),
        },
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("load_signal", _node_load_signal, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("dispatch", _node_dispatch)
    g.add_node("audit", _node_audit)
    g.add_edge(START, "load_signal")
    g.add_edge("load_signal", "dispatch")
    g.add_edge("dispatch", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="notify_company")
