# lg-jukyu — LangGraph Server actor for jukyu.etzhayyim.com

Global Supply Demand System. OSS LangGraph FastAPI pattern (mirrors lg-yukkuri).

## Layout

```
lg/
├── langgraph.json                           # 12 graphs manifest + crons
├── pyproject.toml
├── Dockerfile                               # OSS, no licensed base
├── lg_jukyu/
│   ├── __init__.py
│   ├── state.py                             # EquilibriumState / CompanyExposure / NotificationSignal / …
│   ├── audit.py                             # fire-and-forget BPMN generic.audit.emit
│   ├── checkpointer.py                      # _RwAsyncPostgresSaver (RW ON CONFLICT 回避)
│   ├── cron.py                              # APScheduler in-process
│   ├── server.py                            # FastAPI: /runs /runs/stream /xrpc/{nsid}
│   │                                        #          /export/brief /extract/shocks
│   │                                        #          /cron/domain-adapter/{domain}
│   └── graphs/
│       ├── health.py                        # com.etzhayyim.apps.jukyu.health
│       ├── query_balance.py                 # com.etzhayyim.apps.jukyu.queryBalance
│       ├── query_supply_chain.py            # com.etzhayyim.apps.jukyu.querySupplyChain
│       ├── rank_company_exposure.py         # com.etzhayyim.apps.jukyu.rankCompanyExposure
│       ├── explain_node.py                  # com.etzhayyim.apps.jukyu.explainNode
│       ├── run_stress_propagation.py        # com.etzhayyim.apps.jukyu.runStressPropagation
│       ├── upsert_signal.py                 # com.etzhayyim.apps.jukyu.upsertSignal
│       ├── export_brief.py                  # com.etzhayyim.apps.jukyu.exportBrief (gemma-4-e4b-it)
│       ├── notify_company.py                # com.etzhayyim.apps.jukyu.notifyCompany
│       ├── normalize_domain_adapter.py      # com.etzhayyim.apps.jukyu.normalizeDomainAdapter
│       ├── extract_shocks.py                # com.etzhayyim.apps.jukyu.extractShocks (qwen3-30b)
│       └── equilibrium.py                   # resident 15-min loop (cron)
└── tests/
    └── test_smoke.py                        # 25 smoke tests (all pass)
```

## NSID Coverage (11 of 11)

| NSID | assistant_id | graph file | status |
|---|---|---|---|
| `com.etzhayyim.apps.jukyu.health` | `health` | health.py | ✅ |
| `com.etzhayyim.apps.jukyu.queryBalance` | `query_balance` | query_balance.py | ✅ |
| `com.etzhayyim.apps.jukyu.querySupplyChain` | `query_supply_chain` | query_supply_chain.py | ✅ |
| `com.etzhayyim.apps.jukyu.rankCompanyExposure` | `rank_company_exposure` | rank_company_exposure.py | ✅ |
| `com.etzhayyim.apps.jukyu.explainNode` | `explain_node` | explain_node.py | ✅ |
| `com.etzhayyim.apps.jukyu.runStressPropagation` | `run_stress_propagation` | run_stress_propagation.py | ✅ |
| `com.etzhayyim.apps.jukyu.upsertSignal` | `upsert_signal` | upsert_signal.py | ✅ |
| `com.etzhayyim.apps.jukyu.exportBrief` | `export_brief` | export_brief.py | ✅ |
| `com.etzhayyim.apps.jukyu.notifyCompany` | `notify_company` | notify_company.py | ✅ |
| `com.etzhayyim.apps.jukyu.normalizeDomainAdapter` | `normalize_domain_adapter` | normalize_domain_adapter.py | ✅ |
| `com.etzhayyim.apps.jukyu.extractShocks` | `extract_shocks` | extract_shocks.py | ✅ |

Plus 1 internal graph:
| `equilibrium` | resident 15-min Pregel loop (cron, no XRPC) | equilibrium.py | ✅ |

## Pregel Design

Graph: `run_stress_propagation` (synchronous invocation) + `equilibrium` (cron every 15 min)

DAG: `init_run → read_balance → read_chain → parse_scenario → propagate → write_signals → enrich_signals → read_outbox`

Risk score: `0.30×supply + 0.20×demand + 0.20×price + 0.20×downstream + 0.10×structural`
Confidence: `freshness(30%) + reliability(25%) + connectivity(20%) + cargo/price(15%) + corroboration(10%)`
Halting: max 8 supersteps; stop if max delta < 0.03 for 2 consecutive supersteps.

## Cron Schedule

| Graph | Cron | Input |
|---|---|---|
| `equilibrium` | `*/15 * * * *` | `{with_llm: false}` |
| `normalize_domain_adapter` (naphtha) | `7 * * * *` | `{domain: "naphtha"}` |
| `normalize_domain_adapter` (crude_oil) | `17 * * * *` | `{domain: "crude_oil"}` |
| `normalize_domain_adapter` (energy) | `27 */2 * * *` | `{domain: "energy"}` |
| `normalize_domain_adapter` (food) | `37 */2 * * *` | `{domain: "food"}` |
| `normalize_domain_adapter` (metals) | `47 */3 * * *` | `{domain: "metals"}` |
| `normalize_domain_adapter` (logistics) | `57 */3 * * *` | `{domain: "logistics"}` |
| `normalize_domain_adapter` (transport) | `3 */6 * * *` | `{domain: "transport"}` |

## LLM Models

| Role | Model | Trigger |
|---|---|---|
| Shock extraction / scenario parsing | `qwen3-30b` | `extractShocks`, `runStressPropagation` with `scenarioText` |
| Narrative brief | `gemma-4-e4b-it` | `exportBrief`, `runStressPropagation` with `withLLM=true` |

## Env Vars

| Var | Default | Purpose |
|---|---|---|
| `RW_URL` / `LG_CHECKPOINTER_URL` | (required) | RisingWave PG :4566 |
| `JUKYU_APP_DID` | `did:web:jukyu.etzhayyim.com` | Actor DID for audit |
| `JUKYU_LLM_URL` | `http://llm.etzhayyim.com` | LiteLLM gateway |
| `JUKYU_LLM_API_KEY` | `""` | Bearer token |
| `JUKYU_LLM_EXTRACTION_MODEL` | `qwen3-30b` | Shock extraction model |
| `JUKYU_LLM_NARRATIVE_MODEL` | `gemma-4-e4b-it` | Narrative model |
| `JUKYU_LLM_TIMEOUT` | `30` | LLM request timeout (sec) |
| `JUKYU_LLM_ENRICH_MAX` | `10` | Max signals to enrich per run |
| `LG_API_KEY` | `""` | Optional /runs auth key |
| `LG_CRON_ENABLED` | `true` | Disable crons on N-1 replicas |

## Phases

| Phase | Scope | Status |
|---|---|---|
| **P1** LangGraph scaffold | 12 graphs + server + Dockerfile + langgraph.json | ✅ 2026-05-15 |
| **P1** DB schema | `vertex_jukyu_*`, `edge_jukyu_*`, `mv_jukyu_*` | ✅ migrations at `30-graph/graph-schema/migrations/20260514153000_jukyu_global_supply_demand_sos.ts` + `202605150002_jukyu_entity_vessel_transport.ts` |
| **P1** Helm chart | `50-infra/vultr/lg-jukyu-pool/` | ✅ deployment.yaml + cronjob.yaml |
| **P1** build + push amd64 | `ghcr.io/etzhayyim/kotodama:jukyu-entity-transport-*-amd64` | ✅ uses shared kotodama image (values.yaml pinned) |
| **P1** CF tunnel route | cloudflared ConfigMap jukyu NSID routes | ✅ 2026-05-15 added to bpmn-dispatcher-tunnel.yaml |
| **P2** naphtha MV connection | live `mv_naphtha_*` → jukyu normalization | ⏳ |
| **P2** UI cockpit | SvelteKit balance/chain/company/scenario views | ✅ `60-apps/etzhayyim-project-jukyu/appview/jukyu-ui-jukyu001/svelte/src/App.svelte` |
| **P3** non-naphtha adapters | crude_oil, energy, food, metals, logistics, transport (semiconductor runs via transport loop) | ✅ domain adapters implemented in `normalize_domain_adapter.py`; MCP dispatch routes: all 7 domains; K8s CronJobs: naphtha, energy, food, metals, logistics, transport (crude_oil via transport loop) |
