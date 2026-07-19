# lg-jukyu (clj twin) — LangGraph python → clj port (ADR-2606280030)

Clojure-on-babashka twin of `../lg/` (the deployed FastAPI + RisingWave pod). This
twin is **ADDITIVE and COEXISTS** with the Python runtime — `langgraph.json` /
`Dockerfile` / Helm still ship the Python pod; nothing here touches it.

## Run

```bash
cd 60-apps/etzhayyim-project-jukyu/lg-clj
bb test            # or: bb run_tests.clj   (45 tests / 147 assertions green)
```

## Layout

```
lg-clj/
├── bb.edn                       # langgraph-clj + langchain-clj pinned (scoped; ≠ repo-root bb.edn)
├── run_tests.clj                # repo rule: .clj runner, NOT .sh
├── src/lg_jukyu/
│   ├── util.cljc                # now-iso / severity / numeric coercion / round4
│   ├── audit.cljc               # fire-and-forget audit (injectable *audit-sink*, default no-op)
│   ├── llm.cljc                 # Murakumo loopback chat edge (*chat*) + assert-murakumo
│   ├── store.cljc               # INJECTABLE store seam (RisingWave→kotoba-Datom-log target)
│   ├── pregel.cljc              # VERIFIABLE Pregel core: risk weights + confidence + halting
│   ├── cron.cljc                # cron specs (byte-faithful to langgraph.json) + fire!
│   ├── server.cljc              # GRAPHS / NSID-MAP / dispatch + handle-request + httpkit serve
│   └── graphs/*.cljc            # 12 StateGraphs (one per python graph)
└── test/lg_jukyu/smoke_test.cljc
```

## Faithful mapping + deviations

- **Topology** — every StateGraph mirrors the python node DAG exactly (health 3-node,
  query/rank/upsert/extract 2-node, explain/notify 3-node, export 3-node,
  run_stress_propagation 9-node, equilibrium 7-node).
- **Pregel core** (`pregel.cljc`) ports `propagate` exactly: risk =
  `0.30·supply+0.20·demand+0.20·price+0.20·downstream+0.10·structural`; confidence =
  `freshness(30)+reliability(25)+connectivity(20)+cargo/price(15)+corroboration(10)`;
  halt after 2 consecutive supersteps with max-delta < 0.03 (≤ max_iterations).
- **RisingWave/psycopg → `store/*` seam** (substrate boundary forbids RisingWave;
  target = kotoba Datom log). Defaults return `"store not configured"` — exact parity
  with the python `RW_URL`-unset guard. Tests rebind to in-memory stubs.
- **LiteLLM gateway → Murakumo loopback** (`llm.cljc`, ADR-2605215000): default
  `http://127.0.0.1:4000`, `assert-murakumo` refuses off-fleet hosts. Models preserved
  (qwen3-30b extraction / gemma-4-e4b-it narrative).
- **httpx audit → injectable `*audit-sink*`** (default no-op, fire-and-forget parity).
- **FastAPI/uvicorn → `handle-request` ring dispatcher** + optional `serve` on
  `org.httpkit.server` (deployment-deferred; the live pod stays the runtime).
- **No RetryPolicy in langgraph-clj** — the python `RetryPolicy(max_attempts=…)` on DB
  nodes has no clj analogue (the retried op is now an injectable seam). Noted, not ported.
- **`/runs/stream` SSE** is out of scope for the twin (deferred to the live pod).
```
