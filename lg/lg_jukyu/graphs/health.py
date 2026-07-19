"""jukyu `health` graph — RW probe + liveness.

NSID: com.etzhayyim.apps.jukyu.health
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
    ok: bool
    rw_ok: bool
    rw_latency_ms: int
    server_now: str
    error: str | None


async def _node_check_rw(state: _State) -> dict[str, Any]:
    if not _RW_URL:
        return {"rw_ok": False, "error": "RW_URL not set"}
    try:
        import psycopg
        started = time.monotonic()
        conn = await psycopg.AsyncConnection.connect(_RW_URL, autocommit=True, connect_timeout=5)
        try:
            cur = conn.cursor()
            await cur.execute("SELECT 1")
            await cur.fetchone()
        finally:
            await conn.close()
        return {"rw_ok": True, "rw_latency_ms": int((time.monotonic() - started) * 1000)}
    except Exception as exc:  # noqa: BLE001
        return {"rw_ok": False, "error": f"rw: {exc!s}"[:200]}


async def _node_summarize(state: _State) -> dict[str, Any]:
    return {
        "ok": bool(state.get("rw_ok")),
        "server_now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


async def _node_audit(state: _State) -> dict[str, Any]:
    emit_audit_bg(
        actor=_APP_DID,
        activity="jukyu.health.check",
        object_id=f"health:{int(time.time())}",
        object_type="jukyu.health",
        attributes={"ok": state.get("ok", False), "rwOk": state.get("rw_ok", False)},
    )
    return {}


def _build() -> StateGraph:
    g: StateGraph = StateGraph(_State)
    g.add_node("check_rw", _node_check_rw, retry_policy=RetryPolicy(max_attempts=2))
    g.add_node("summarize", _node_summarize)
    g.add_node("audit", _node_audit)
    g.add_edge(START, "check_rw")
    g.add_edge("check_rw", "summarize")
    g.add_edge("summarize", "audit")
    g.add_edge("audit", END)
    return g


GRAPH = _build().compile(name="health")
