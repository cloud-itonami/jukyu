# Operator quickstart — jukyu

Every command below was run from a clean clone of `cloud-itonami/jukyu` at
`05c8501c` on 2026-08-19 (UTC), on macOS 25.3.0 with babashka 1.12.218,
node 26.3.0, Python 3.14.5, pnpm 10. The output shown is what came back.

Steps 1–5 work. Steps 6 and 7 **fail**, and they are here so you learn that in one
command instead of an afternoon — each one prints the exact error and
[`../README.md`](../README.md) explains the cause.

Run everything from the repository root unless a step says otherwise.

---

## 1. Confirm you have the tree this document describes

```bash
git log --oneline | tail -1         # 05c8501 chore: extract app repository
git ls-files | wc -l                # 77
ls                                  # CLAUDE.md  JUKYU_DESIGN.md  NOTICE
                                    # README.edn  README.md  appview  docs
                                    # kotoba  lg  lg-clj  migration.edn
```

`05c8501` is the extraction commit and holds 75 of those 77 files; the other two
are this quickstart and `README.md`. If `git log` shows work after them, the
numbers below may have moved — re-derive them rather than trusting this file.

## 2. Run the Clojure suite (the fastest signal that anything works)

```bash
cd lg-clj && bb test && cd ..
```

Expected, and what you should hold this repo to:

```
Testing lg-jukyu.smoke-test

Ran 50 tests containing 160 assertions.
0 failures, 0 errors.
```

`bb run_tests.clj` is the same thing without the task wrapper. `bb tasks` lists
`test` and `server`. First run downloads two git dependencies
(`langchain-clj`, `langgraph-clj`, both pinned by sha in `bb.edn`) and takes a
minute; later runs are seconds.

Note the count: `lg-clj/CLAUDE.md` still advertises 45 tests / 147 assertions.
50 / 160 is correct.

## 3. Start the dispatch surface and check every branch of it

```bash
cd lg-clj
LG_API_KEY=jukyu-walk-key bb run_tests.clj --server 8971 &
cd ..
```

The port is yours to choose; `run_tests.clj` defaults to 2027 when you omit it.
Setting `LG_API_KEY` is what arms the `/runs` guard — leave it unset and every
key is accepted (`server/check-api-key` only compares when the key is non-empty).

```bash
B=http://127.0.0.1:8971

curl -s $B/health
curl -s $B/ok
```

```json
{"ok":true,"graphs":["export_brief","health","explain_node","extract_shocks",
"upsert_signal","rank_company_exposure","run_stress_propagation","query_balance",
"equilibrium","normalize_domain_adapter","notify_company","query_supply_chain"],
"version":"0.1.0"}
```

Twelve graphs, matching `langgraph.json` on the Python side.

```bash
# authenticated run
curl -s -X POST $B/runs -H 'content-type: application/json' \
     -H 'x-api-key: jukyu-walk-key' -d '{"assistant_id":"health","input":{}}'
# → 200 {"rw_ok":false,"error":"store not configured","ok":false,"server_now":"…"}

# wrong key
curl -s -o /dev/null -w '%{http_code}\n' -X POST $B/runs \
     -H 'content-type: application/json' -H 'x-api-key: nope' \
     -d '{"assistant_id":"health","input":{}}'
# → 401   body {"detail":"invalid x-api-key"}

# unknown graph
curl -s -X POST $B/runs -H 'content-type: application/json' \
     -H 'x-api-key: jukyu-walk-key' -d '{"assistant_id":"nope","input":{}}'
# → 404 {"error":"unknown graph: nope"}

# XRPC is unauthenticated by design (trust sits at the tunnel), camelCase in
curl -s -X POST $B/xrpc/com.etzhayyim.apps.jukyu.queryBalance \
     -H 'content-type: application/json' \
     -d '{"domain":"naphtha","countryCode":"JP","limit":5}'
# → 200 {"domain":"naphtha","country_code":"JP","limit":5,
#        "error":"store not configured","rows":[]}

curl -s -X POST $B/xrpc/com.etzhayyim.apps.jukyu.nope \
     -H 'content-type: application/json' -d '{}'
# → 404 {"error":"unknown NSID: com.etzhayyim.apps.jukyu.nope"}

curl -s $B/nope
# → 404 {"detail":"not found"}
```

Two things to take from this. `countryCode` came back as `country_code`: the
dispatcher coerces camelCase to snake_case (`server/camel->snake`) so the XRPC
surface and the graph inputs can differ. And **`"store not configured"` is the
designed answer, not a fault** — see step 4.

Stop the server when you are done:

```bash
pkill -f 'run_tests.clj --server 8971'
```

## 4. Make the Pregel core produce actual numbers

Every read and write lives in `lg-clj/src/lg_jukyu/store.cljc` as an unbound
dynamic var returning `"store not configured"` — the same thing the Python server
does with `RW_URL` unset. Bind the seam and the graphs run end to end. Save this
as `/tmp/jukyu-pregel-demo.clj`:

```clojure
(require '[lg-jukyu.pregel :as pregel]
         '[lg-jukyu.store :as store]
         '[lg-jukyu.graphs.equilibrium :as equil]
         '[langgraph.graph :as g])

(def nodes [{:nodeId "JP-NAPHTHA-01" :domain "naphtha" :countryCode "JP"
             :operatorDid "did:web:refinery-a.example" :supplyCapacity 100
             :demandCapacity 150 :confidence 0.5}
            {:nodeId "JP-NAPHTHA-02" :domain "naphtha" :countryCode "JP"
             :operatorDid "did:web:cracker-b.example" :supplyCapacity 100
             :demandCapacity 100 :confidence 0.5}])
(def edges [{:src "JP-NAPHTHA-01" :dst "JP-NAPHTHA-02"
             :dependencyWeight 0.8 :confidence 0.9}])
(def balance [{:domain "naphtha" :countryCode "JP" :supplyQuantity 100
               :demandQuantity 150 :balanceQuantity -50 :confidence 0.7}])

(println "risk weights      :" pregel/risk-weights)
(println "compute-risk 1.0  :" (pregel/compute-risk {:supply 1.0}))

(let [out (pregel/propagate-full {:supply_nodes nodes :supply_edges edges
                                  :balance_rows balance :shock_seeds {}
                                  :max_iterations 8})]
  (println "superstep         :" (:superstep out) " converged:" (:converged out))
  (doseq [e (:company_exposures out)]
    (println "  exposure        :" (:companyDid e)
             "risk" (:riskScore e) "conf" (:confidence e))))

(binding [store/*read-balance-rows*   (fn [_] {:rows balance})
          store/*read-chain-rows*     (fn [_] {:nodes nodes :edges edges})
          store/*write-signals-batch* (fn [_ _ ex] {:written (count ex)})
          store/*outbox-pending-count* (fn [] 3)]
  (let [out (g/invoke equil/GRAPH {})]
    (println "equilibrium run_id:" (:run_id out))
    (println "signals_written   :" (:signals_written out))
    (println "outbox_count      :" (:outbox_count out))))
```

```bash
cd lg-clj && bb /tmp/jukyu-pregel-demo.clj && cd ..
```

```
risk weights      : {:supply 0.3, :demand 0.2, :price 0.2, :downstream 0.2, :structural 0.1}
compute-risk 1.0  : 0.3
superstep         : 8  converged: true
  exposure        : did:web:cracker-b.example risk 0.6648 conf 0.6732
  exposure        : did:web:refinery-a.example risk 0.45 conf 0.6732
equilibrium run_id: jukyu.equil.2026-08-19T00:49:59Z
signals_written   : 2
outbox_count      : 3
```

`run_id` carries the current time, so yours will differ; the risk and confidence
numbers should not. `n1` is short 50 units of supply, which seeds supply pressure,
and the dependency edge carries that pressure downstream to `n2` — which is why
the *downstream* company ranks above the constrained one. Exposures come back
sorted by risk descending, and `propagate-full` is deterministic across runs
(`smoke_test.cljc` asserts that).

**Then check that the number means something.** A propagation that ignores its
input would print the same figures, so reverse the edge and drop it:

```bash
cd lg-clj && bb -e '
(require (quote [lg-jukyu.pregel :as pregel]))
(def nodes [{:nodeId "n1" :domain "naphtha" :countryCode "JP" :operatorDid "did:web:refinery-a.example"
             :supplyCapacity 100 :demandCapacity 150 :confidence 0.5}
            {:nodeId "n2" :domain "naphtha" :countryCode "JP" :operatorDid "did:web:cracker-b.example"
             :supplyCapacity 100 :demandCapacity 100 :confidence 0.5}])
(def balance [{:domain "naphtha" :countryCode "JP" :supplyQuantity 100 :demandQuantity 150
               :balanceQuantity -50 :confidence 0.7}])
(defn run [edges]
  (->> (pregel/propagate-full {:supply_nodes nodes :supply_edges edges :balance_rows balance
                               :shock_seeds {} :max_iterations 8})
       :company_exposures (map (juxt :companyDid :riskScore))))
(println "n1->n2 :" (run [{:src "n1" :dst "n2" :dependencyWeight 0.8 :confidence 0.9}]))
(println "n2->n1 :" (run [{:src "n2" :dst "n1" :dependencyWeight 0.8 :confidence 0.9}]))
(println "no edge:" (run []))' && cd ..
```

```
n1->n2 : ([did:web:cracker-b.example 0.6648] [did:web:refinery-a.example 0.45])
n2->n1 : ([did:web:refinery-a.example 0.6432] [did:web:cracker-b.example 0.3])
no edge: ([did:web:refinery-a.example 0.45] [did:web:cracker-b.example 0.3])
```

The ranking follows the edge. `n1` is the node short 50 units of supply, so with
no edge it carries its own imbalance (0.45) and `n2` sits at the floor (0.3).
Point the dependency at `n2` and `n2` inherits the pressure and overtakes it;
point it back and the order flips. That is the downstream term of the risk
formula doing its job, and it is why a *downstream* company can rank above the
constrained one.

To wire a real backend, bind the same vars at your deployment layer. Nothing in
`graphs/` reaches past the seam.

## 5. Run the Python suite

This is the tree the Kubernetes manifests actually deploy.

```bash
python3 -m venv /tmp/jukyu-venv
cd lg && /tmp/jukyu-venv/bin/pip install -e '.[dev]' && \
  /tmp/jukyu-venv/bin/python -m pytest -q && cd ..
```

```
25 passed
```

The tests are import/structure/cron-config only — no database and no LLM. Running
the server itself needs `LG_CHECKPOINTER_URL` or `RW_URL` pointing at RisingWave;
`checkpointer.build_checkpointer` raises `RuntimeError` without one, on purpose.

**Check what the install pulled in:**

```bash
/tmp/jukyu-venv/bin/pip show kotodama | head -3
```

```
Name: kotodama
Version: 0.0.18
Summary: 日本語の動詞を活用形に変換する
```

That is a third-party Japanese-verb-conjugation library, not this workspace's
`kotodama`. `pyproject.toml` declares a bare `kotodama` dependency with no
source and no importer anywhere under `lg/`, so pip resolves the name off PyPI.
The 25 tests pass with or without it. Do not build a container from this
`pyproject.toml` without deciding what that line was meant to say.

## 6. `kotoba/` — expected to fail, twice

There are two blockers here, and the first one hides the second.

```bash
cd kotoba && pnpm install; cd ..
```

```
ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED  Failed to prepare git-hosted package
  fetched from "git@github.com:etzhayyim/com-etzhayyim-sdk.git": The git-hosted
  package "@etzhayyim/sdk@0.1.0-alpha" needs to execute build scripts but is not
  in the "onlyBuiltDependencies" allowlist.
```

`@etzhayyim/sdk` is a git dependency that has to be built after checkout, and
`kotoba/` ships no `pnpm-workspace.yaml` to allow it. (The sibling
`appview/jukyu-ui-jukyu001/svelte/` does have one, allowing `esbuild` — so the
pattern exists in this repo, just not here.) Get past it and you land on the real
wall:

```bash
cd kotoba && pnpm install --ignore-scripts; cd ..
```

```
ERR_PNPM_MISSING_PACKAGE_NAME  Can't install
  git+https://github.com/kotoba-lang/ipfs.git#main: Missing package name
```

The chain is `@etzhayyim/sdk` → `@etzhayyim/checkpointer` → `@etzhayyim/ipfs`,
and that last repository (now `kotoba-lang/io-ipfs`) publishes a `package.json`
with no `name` field. Nothing is written to `node_modules` in either case.

So `pnpm test` and `pnpm typecheck` cannot run, and `test/jukyu.test.ts` has never
executed from this repository. Read `src/registry.ts` for the intended contract:
supply nodes and balance observations go through `sdk.write`/`sdk.read` in
plaintext, per-company exposure through `sdk.encryptedWrite`/`encryptedRead`.

## 7. `appview/` — expected to fail

```bash
cd appview/jukyu-ui-jukyu001/svelte && pnpm install; cd -
```

```
ERR_PNPM_LINKED_PKG_DIR_NOT_FOUND  Could not install from
  "/com-etzhayyim-svelte-design-system" as it does not exist.
```

`@etzhayyim/design-system` is a `file:` path with six `../` segments, which lands
on the filesystem root from this layout. The design system is west-registered at
`orgs/kotoba-lang/svelte-design-system`.

Do not try `wrangler deploy` either: `wrangler.jsonc` `alias` names seven absolute
paths under `/Users/junkawasaki/etzhayyim/etzhayyim-apps-etzhayyim/…`, a directory
that does not exist, and `assets.directory` points at the uncommitted
`./svelte/build` that step 7 cannot produce.

If you do get the UI running, read `svelte/src/App.svelte` first: it renders from
hardcoded `fallback*` arrays and labels the state `"<domain> fallback snapshot"`.
Those numbers are placeholders, not observations.

## 8. What you cannot reach from here

```bash
dig +short jukyu.etzhayyim.com jukyu001.etzhayyim.com    # both empty
dig +short etzhayyim.com                                 # resolves via Cloudflare
```

Neither actor host resolves, so `did:web:jukyu.etzhayyim.com` cannot be resolved
either. `CLAUDE.md` and `lg/CLAUDE.md` both describe a running pod as the live
runtime; from outside the cluster you cannot confirm or refute that, and this
quickstart does not claim to. The deployment manifests are in `etzhayyim/root` at
`50-infra/k8s/lg-jukyu/` — read them at their own tip.

## Where to go next

- `lg-clj/src/lg_jukyu/pregel.cljc` — the risk and confidence formulas, no I/O
- `lg-clj/src/lg_jukyu/store.cljc` — the seam to bind for a real backend
- `lg-clj/test/lg_jukyu/smoke_test.cljc` — 50 tests, and the reference for how to
  stub the store per graph
- `lg/langgraph.json` — the 12 graphs and 8 cron schedules the cluster runs
- `CLAUDE.md` / `JUKYU_DESIGN.md` — intent and the graph/MCP contract; check
  `../README.md` for which of their paths and counts have gone stale
