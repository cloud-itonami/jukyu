"""OSS FastAPI server for lg-jukyu (mirrors lg-yukkuri pattern).

Endpoints:
  POST /runs                          → invoke a graph synchronously
  POST /runs/stream                   → stream graph events as SSE
  POST /xrpc/{nsid}                   → XRPC-compat shim (NSID → assistant_id)
  POST /export/brief                  → LLM executive brief (gemma-4-e4b-it)
  POST /extract/shocks                → LLM shock extraction (qwen3-30b)
  POST /cron/domain-adapter/{domain}  → trigger domain adapter normalization
  GET  /threads/{tid}/state           → fetch latest checkpoint
  GET  /ok / /health                  → liveness / readiness

Auth: optional `LG_API_KEY` env enforces `x-api-key` on /runs paths.
/xrpc/{nsid} is unauthenticated (trust at the cloudflared tunnel layer).

NSID surface: 10 jukyu MCP endpoints mapped to 12 graphs (+ equilibrium + extract_shocks).
"""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Path as FPath
from fastapi.responses import StreamingResponse

from lg_jukyu.checkpointer import build_checkpointer
from lg_jukyu.cron import start_cron, stop_cron
from lg_jukyu.graphs.equilibrium import GRAPH as EQUILIBRIUM
from lg_jukyu.graphs.explain_node import GRAPH as EXPLAIN_NODE
from lg_jukyu.graphs.export_brief import GRAPH as EXPORT_BRIEF
from lg_jukyu.graphs.extract_shocks import GRAPH as EXTRACT_SHOCKS
from lg_jukyu.graphs.health import GRAPH as HEALTH
from lg_jukyu.graphs.normalize_domain_adapter import GRAPH as NORMALIZE_DOMAIN_ADAPTER
from lg_jukyu.graphs.notify_company import GRAPH as NOTIFY_COMPANY
from lg_jukyu.graphs.query_balance import GRAPH as QUERY_BALANCE
from lg_jukyu.graphs.query_supply_chain import GRAPH as QUERY_SUPPLY_CHAIN
from lg_jukyu.graphs.rank_company_exposure import GRAPH as RANK_COMPANY_EXPOSURE
from lg_jukyu.graphs.run_stress_propagation import GRAPH as RUN_STRESS_PROPAGATION
from lg_jukyu.graphs.upsert_signal import GRAPH as UPSERT_SIGNAL

_log = logging.getLogger(__name__)

GRAPHS: dict[str, Any] = {
    "health":                   HEALTH,
    "query_balance":            QUERY_BALANCE,
    "query_supply_chain":       QUERY_SUPPLY_CHAIN,
    "rank_company_exposure":    RANK_COMPANY_EXPOSURE,
    "explain_node":             EXPLAIN_NODE,
    "run_stress_propagation":   RUN_STRESS_PROPAGATION,
    "upsert_signal":            UPSERT_SIGNAL,
    "export_brief":             EXPORT_BRIEF,
    "notify_company":           NOTIFY_COMPANY,
    "normalize_domain_adapter": NORMALIZE_DOMAIN_ADAPTER,
    "extract_shocks":           EXTRACT_SHOCKS,
    "equilibrium":              EQUILIBRIUM,
}

_API_KEY = os.environ.get("LG_API_KEY", "").strip()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    cp_ctx = build_checkpointer()
    cp = await cp_ctx.__aenter__()
    app.state.checkpointer = cp
    app.state.cp_ctx = cp_ctx

    bound: dict[str, Any] = {}
    for name, g in GRAPHS.items():
        try:
            bound[name] = g.with_config({"checkpointer": cp})
        except Exception:  # noqa: BLE001
            try:
                g.checkpointer = cp
            except Exception:
                pass
            bound[name] = g
    app.state.graphs = bound

    scheduler = start_cron(bound)
    app.state.scheduler = scheduler

    _log.info("lg-jukyu server up: graphs=%s crons=%s", list(bound), bool(scheduler))
    try:
        yield
    finally:
        await stop_cron(scheduler)
        await cp_ctx.__aexit__(None, None, None)


app = FastAPI(title="lg-jukyu OSS server", version="0.1.0", lifespan=_lifespan)


def _require_api_key(x_api_key: str | None = Header(default=None, alias="x-api-key")) -> None:
    if _API_KEY and x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="invalid x-api-key")


@app.get("/ok")
async def ok() -> dict[str, Any]:
    return {"ok": True, "graphs": list(GRAPHS.keys()), "version": "0.1.0"}


@app.get("/health")
async def health() -> dict[str, Any]:
    cp_ok = hasattr(app.state, "checkpointer") and app.state.checkpointer is not None
    return {"ok": cp_ok, "checkpointer": cp_ok}


@app.post("/runs", dependencies=[Depends(_require_api_key)])
async def create_run(body: dict[str, Any]) -> dict[str, Any]:
    assistant_id = str(body.get("assistant_id") or "")
    if assistant_id not in app.state.graphs:
        raise HTTPException(status_code=404, detail=f"unknown graph: {assistant_id}")
    graph = app.state.graphs[assistant_id]
    input_data = body.get("input") or {}
    config = body.get("config") or {}
    started = time.monotonic()
    try:
        result = await graph.ainvoke(input_data, config=config)
        return {
            "ok": True, "result": result, "assistantId": assistant_id,
            "latencyMs": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        _log.exception("graph %s failed", assistant_id)
        return {
            "ok": False, "error": str(exc)[:500],
            "errorType": type(exc).__name__, "assistantId": assistant_id,
            "latencyMs": int((time.monotonic() - started) * 1000),
        }


@app.post("/runs/stream", dependencies=[Depends(_require_api_key)])
async def stream_run(body: dict[str, Any]) -> StreamingResponse:
    assistant_id = str(body.get("assistant_id") or "")
    if assistant_id not in app.state.graphs:
        raise HTTPException(status_code=404, detail=f"unknown graph: {assistant_id}")
    graph = app.state.graphs[assistant_id]
    input_data = body.get("input") or {}
    config = body.get("config") or {}
    stream_mode = body.get("stream_mode") or "values"

    async def _gen() -> AsyncIterator[bytes]:
        try:
            async for chunk in graph.astream(input_data, config=config, stream_mode=stream_mode):
                yield f"data: {json.dumps({'event':'values','data':_safe_json(chunk)})}\n\n".encode()
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'event':'error','data':str(exc)[:500]})}\n\n".encode()

    return StreamingResponse(_gen(), media_type="text/event-stream")


# ── Dedicated endpoints for non-XRPC surfaces ────────────────────────────

@app.post("/export/brief")
async def export_brief(body: dict[str, Any]) -> dict[str, Any]:
    """LLM executive brief from latest outbox (gemma-4-e4b-it)."""
    graph = app.state.graphs["export_brief"]
    input_data = {_camel_to_snake(k): v for k, v in (body or {}).items()}
    thread_id = f"export_brief:{int(time.time()) // 900}"
    config = {"configurable": {"thread_id": thread_id}}
    started = time.monotonic()
    try:
        result = await graph.ainvoke(input_data, config=config)
    except Exception as exc:  # noqa: BLE001
        _log.exception("export_brief failed")
        return {"error": str(exc)[:300], "latencyMs": int((time.monotonic() - started) * 1000)}
    out = dict(result) if isinstance(result, dict) else {"result": _safe_json(result)}
    out["latencyMs"] = int((time.monotonic() - started) * 1000)
    return out


@app.post("/extract/shocks")
async def extract_shocks(body: dict[str, Any]) -> dict[str, Any]:
    """News text → structured shock events (qwen3-30b)."""
    graph = app.state.graphs["extract_shocks"]
    input_data = {_camel_to_snake(k): v for k, v in (body or {}).items()}
    thread_id = f"extract_shocks:{int(time.time())}"
    config = {"configurable": {"thread_id": thread_id}}
    started = time.monotonic()
    try:
        result = await graph.ainvoke(input_data, config=config)
    except Exception as exc:  # noqa: BLE001
        _log.exception("extract_shocks failed")
        return {"error": str(exc)[:300], "latencyMs": int((time.monotonic() - started) * 1000)}
    out = dict(result) if isinstance(result, dict) else {"result": _safe_json(result)}
    out["latencyMs"] = int((time.monotonic() - started) * 1000)
    return out


@app.post("/cron/domain-adapter/{domain}")
async def trigger_domain_adapter(
    domain: str = FPath(..., description="Domain name e.g. naphtha, crude_oil, energy"),
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Trigger single domain adapter normalization."""
    graph = app.state.graphs["normalize_domain_adapter"]
    input_data = {_camel_to_snake(k): v for k, v in (body or {}).items()}
    input_data.setdefault("domain", domain)
    thread_id = f"domain_adapter:{domain}:{int(time.time())}"
    config = {"configurable": {"thread_id": thread_id}}
    started = time.monotonic()
    try:
        result = await graph.ainvoke(input_data, config=config)
    except Exception as exc:  # noqa: BLE001
        _log.exception("domain adapter %s failed", domain)
        return {"error": str(exc)[:300], "domain": domain,
                "latencyMs": int((time.monotonic() - started) * 1000)}
    out = dict(result) if isinstance(result, dict) else {"result": _safe_json(result)}
    out["latencyMs"] = int((time.monotonic() - started) * 1000)
    return out


# ── XRPC-compat surface ────────────────────────────────────────────────

_NSID_TO_ASSISTANT: dict[str, str] = {
    "com.etzhayyim.apps.jukyu.health":                "health",
    "com.etzhayyim.apps.jukyu.queryBalance":          "query_balance",
    "com.etzhayyim.apps.jukyu.querySupplyChain":      "query_supply_chain",
    "com.etzhayyim.apps.jukyu.rankCompanyExposure":   "rank_company_exposure",
    "com.etzhayyim.apps.jukyu.explainNode":           "explain_node",
    "com.etzhayyim.apps.jukyu.runStressPropagation":  "run_stress_propagation",
    "com.etzhayyim.apps.jukyu.upsertSignal":          "upsert_signal",
    "com.etzhayyim.apps.jukyu.exportBrief":           "export_brief",
    "com.etzhayyim.apps.jukyu.notifyCompany":         "notify_company",
    "com.etzhayyim.apps.jukyu.normalizeDomainAdapter": "normalize_domain_adapter",
    "com.etzhayyim.apps.jukyu.extractShocks":         "extract_shocks",
}


def _camel_to_snake(s: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(s):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


@app.post("/xrpc/{nsid}")
async def xrpc_compat(nsid: str, body: dict[str, Any]) -> dict[str, Any]:
    assistant_id = _NSID_TO_ASSISTANT.get(nsid)
    if not assistant_id:
        raise HTTPException(status_code=404, detail=f"unknown NSID: {nsid}")
    if assistant_id not in app.state.graphs:
        raise HTTPException(status_code=503, detail=f"graph not loaded: {assistant_id}")

    graph = app.state.graphs[assistant_id]
    graph_input = {_camel_to_snake(k): v for k, v in (body or {}).items()}
    bucket = int(time.time()) // 1800
    thread_id = f"xrpc:{nsid.split('.')[-1]}:{bucket}"
    config = {"configurable": {"thread_id": thread_id}}

    started = time.monotonic()
    try:
        result = await graph.ainvoke(graph_input, config=config)
    except Exception as exc:  # noqa: BLE001
        _log.exception("xrpc graph %s failed", assistant_id)
        return {
            "error": f"lg-jukyu {type(exc).__name__}",
            "errorDetail": str(exc)[:300],
            "assistantId": assistant_id,
            "latencyMs": int((time.monotonic() - started) * 1000),
        }

    out = dict(result) if isinstance(result, dict) else {"result": _safe_json(result)}
    out["latencyMs"] = int((time.monotonic() - started) * 1000)
    out["assistantId"] = assistant_id
    return out


@app.get("/threads/{thread_id}/state", dependencies=[Depends(_require_api_key)])
async def get_thread_state(thread_id: str, assistant_id: str) -> dict[str, Any]:
    if assistant_id not in app.state.graphs:
        raise HTTPException(status_code=404, detail=f"unknown graph: {assistant_id}")
    graph = app.state.graphs[assistant_id]
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    return {
        "values": _safe_json(snap.values),
        "next": list(snap.next),
        "tasks": [
            {"id": t.id, "name": t.name, "error": str(t.error) if t.error else None}
            for t in (snap.tasks or [])
        ],
    }


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}B>"
    return repr(value)[:200]
