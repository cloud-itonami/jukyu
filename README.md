# jukyu — global supply–demand System-of-Systems actor

**This repository is `cloud-itonami/jukyu`** (west path `orgs/cloud-itonami/jukyu`).
It was extracted on 2026-07-19 from the etzhayyim monorepo path
`60-apps/etzhayyim-project-jukyu`, and the machine-readable `README.edn` still
names it `com-etzhayyim-app-jukyu` — a name no repository answers to today.

Jukyu normalizes other domain actors' supply/demand output, runs a bounded Pregel
stress propagation over the supply chain, ranks company exposure, and writes
target-company signals to an outbox. It does not own the domain data; the domain
actors stay source of truth. The product intent is in
[`JUKYU_DESIGN.md`](./JUKYU_DESIGN.md); the surface contract is in
[`CLAUDE.md`](./CLAUDE.md).

**Read the "What is stale in the prose here" section before trusting either.**
Both files were written while this code lived in the monorepo, and they describe a
running Kubernetes deployment. From a clone you get neither the cluster nor the
data — you get the compute core, and it is genuinely runnable.

## What is actually in this repository

77 tracked files across four trees. 75 of them arrived in the single
extraction commit `05c8501`; the other two are this README and
`docs/operator-quickstart.md`.

| Tree | What it is | Runs from a clone? |
|---|---|---|
| `lg-clj/` | Clojure/babashka twin — 12 StateGraphs, dispatch surface, Pregel core, injectable store seam | **Yes.** 50 tests / 160 assertions green; HTTP server starts |
| `lg/` | Python FastAPI + LangGraph server — the runtime the manifests deploy | **Yes, for tests.** 25 tests green; the server needs RisingWave |
| `kotoba/` | TypeScript kotoba-substrate registry (public catalog plaintext, per-company exposure E2E-sealed) | **No.** dependency install fails — see below |
| `appview/jukyu-ui-jukyu001/` | Cloudflare Worker facade + Svelte 5 cockpit | **No.** neither the Worker nor the UI can be built as committed |

The two graph implementations are deliberate, not drift: ADR-2606280030 made the
Clojure tree an **additive twin** of the Python one. `lg/` is what the Kubernetes
manifests ship; `lg-clj/` is the substrate-clean port whose data layer is an
injectable seam instead of RisingWave.

## Verified 2026-08-19 (UTC)

macOS 25.3.0 · babashka 1.12.218 · node 26.3.0 · Python 3.14.5 · pnpm 10.

Step-by-step commands and their full output are in
[`docs/operator-quickstart.md`](./docs/operator-quickstart.md). Summary:

```
cd lg-clj && bb test
  → Ran 50 tests containing 160 assertions. 0 failures, 0 errors.

cd lg-clj && LG_API_KEY=… bb run_tests.clj --server 8971
  GET  /health                      → 200, 12 graphs, version 0.1.0
  POST /runs      (correct key)     → 200 {"rw_ok":false,"error":"store not configured",…}
  POST /runs      (wrong key)       → 401 {"detail":"invalid x-api-key"}
  POST /runs      (unknown graph)   → 404 {"error":"unknown graph: nope"}
  POST /xrpc/…queryBalance          → 200 {"rows":[],"error":"store not configured"}
  POST /xrpc/…nope                  → 404 {"error":"unknown NSID: …"}
  GET  /nope                        → 404 {"detail":"not found"}

lg/ in a venv: pip install -e '.[dev]' && pytest -q
  → 25 passed
```

**`store not configured` is the correct answer, not a failure.** Every read and
write in `lg-clj/src/lg_jukyu/store.cljc` is an unbound dynamic var whose default
returns that string — deliberate parity with the Python server's behaviour when
`RW_URL` is unset. Bind the seam and the graphs run end to end; the quickstart
does exactly that and gets real numbers out of the Pregel core:

```
superstep 8, converged true
  did:web:cracker-b.example    risk 0.6648  confidence 0.6732
  did:web:refinery-a.example   risk 0.4500  confidence 0.6732
equilibrium run_id jukyu.equil.2026-08-19T00:49:59Z  signals_written 2  outbox_count 3
```

Risk is `0.30·supply + 0.20·demand + 0.20·price + 0.20·downstream + 0.10·structural`
(`lg_jukyu/pregel.cljc`), confidence is `freshness(30) + reliability(25) +
connectivity(20) + cargo/price(15) + corroboration(10)`, and propagation halts
after two consecutive supersteps with max delta < 0.03.

## Known breakage, with the exact cause

Each of these was reproduced on 2026-08-19; none is a guess.

**1. `kotoba/` cannot install its dependencies — two blockers, in this order.**

```
$ cd kotoba && pnpm install
ERR_PNPM_GIT_DEP_PREPARE_NOT_ALLOWED  … "@etzhayyim/sdk@0.1.0-alpha" needs to
  execute build scripts but is not in the "onlyBuiltDependencies" allowlist.

$ cd kotoba && pnpm install --ignore-scripts
ERR_PNPM_MISSING_PACKAGE_NAME  Can't install
  git+https://github.com/kotoba-lang/ipfs.git#main: Missing package name
```

The first is local: `kotoba/` has no `pnpm-workspace.yaml` allowing the git
dependency to build (the sibling `svelte/` tree has one, allowing `esbuild`).
Past it, the second is upstream. The chain is `kotoba/package.json` → `@etzhayyim/sdk`
(`git+…/etzhayyim/com-etzhayyim-sdk.git#12314a0c…`, which GitHub now redirects to
`kotoba-lang/sdk`) → `@etzhayyim/checkpointer` `#63586c4f…` → `@etzhayyim/ipfs`
`git+…/kotoba-lang/ipfs.git#main`. That last repository has since been renamed
`kotoba-lang/io-ipfs` and its `package.json` carries no `name` field, so pnpm
refuses it. Consequence: `pnpm test` (vitest) and `pnpm typecheck` have no way to
run here, and `kotoba/test/jukyu.test.ts` has never been executed from this repo.

**2. `lg/pyproject.toml` reaches for a stranger's package.**

Line 16 declares a bare `kotodama` dependency with no source. Nothing under
`lg/` imports it — the only other mention in the repository is a container image
name in `lg/CLAUDE.md`. `pip install -e '.[dev]'` therefore resolves it from
PyPI and installs **`kotodama 0.0.18`, "日本語の動詞を活用形に変換する" by
Yoshiki Ohira** — an unrelated third-party library that happens to hold the name
this workspace uses internally. Verified present in the venv after install. The
25 tests pass with or without it.

**3. The Cloudflare Worker cannot be built by anyone.**

`appview/jukyu-ui-jukyu001/wrangler.jsonc` has an `alias` map with seven absolute
paths under `/Users/junkawasaki/etzhayyim/etzhayyim-apps-etzhayyim/…`. That
directory does not exist (the monorepo it names was retired). The config also
serves `assets.directory: "./svelte/build"`, which is not committed.

**4. The Svelte cockpit cannot be built either.**

```
$ cd appview/jukyu-ui-jukyu001/svelte && pnpm install
ERR_PNPM_LINKED_PKG_DIR_NOT_FOUND  Could not install from
  "/com-etzhayyim-svelte-design-system" as it does not exist.
```

`@etzhayyim/design-system` is declared as
`file:../../../../../../com-etzhayyim-svelte-design-system` — six levels up from
`svelte/`, which in this repository's layout lands on the filesystem root. The
design system is west-registered at `orgs/kotoba-lang/svelte-design-system`.

**5. The UI shows numbers that are not measurements.** `svelte/src/App.svelte`
initialises `balanceRows` / `chainRows` / `exposureRows` / `nodeLayout` from
hardcoded `fallback*` arrays and sets `status = '<domain> fallback snapshot'`. It
contacts the API only when an operator presses a button. A screenshot of this
cockpit is not evidence that any backend answered — the status line says so, and
so does this README.

**6. `jukyu.etzhayyim.com` does not resolve.** `dig +short` returns nothing for
both `jukyu.etzhayyim.com` and `jukyu001.etzhayyim.com` (`etzhayyim.com` itself
resolves through Cloudflare). So `did:web:jukyu.etzhayyim.com` — the actor DID
that `CLAUDE.md`, `wrangler.jsonc` and `lg-clj/run_tests.clj` all default to —
cannot be resolved from this workstation, and the "live pod" both CLAUDE.md files
call the deployed runtime is not reachable from here. This is a measurement taken
from outside; it says nothing about whether a cluster is running.

**7. `NOTICE` points at a file that is not here.** It conditions use on the
"etzhayyim Charter Compliance Rider v3.1 (see CHARTER-RIDER.md)". No
`CHARTER-RIDER.md` is tracked in this repository. The rider is
ADR-2605192200 (below); sibling components in `etzhayyim/root` each ship a copy
at `<component>/CHARTER-RIDER.md`.

## Where the surrounding pieces live

Everything this repository cites by ADR number lives in **`etzhayyim/root`**
(west path `orgs/etzhayyim/root`), under `90-docs/adr/`:

| Cited as | File |
|---|---|
| ADR-2606280030 | `2606280030-60apps-e7m-dataset-langgraph-python-to-clj-full-migration.edn` |
| ADR-2605215000 | `2605215000-etzhayyim-inference-murakumo-only-no-runpod.edn` |
| ADR-2605181100 | `2605181100-mst-encrypted-records-signal-keywrap.edn` |
| ADR-2605231525 | `2605231525-no-server-key-religious-corp-architecture.edn` |
| ADR-2605172000 | `2605172000-etzhayyim-kotoba-substrate.edn` |
| ADR-2605152300 | `2605152300-jukyu-mcp-query-surface.edn` |
| ADR-2605192100 / 2605192200 / 2606062100 / 2606082400 | charter + rider chain |

The Kubernetes deployment is also in `etzhayyim/root`, but **not at the path
`lg/CLAUDE.md` gives**. It is `50-infra/k8s/lg-jukyu/`
(`deployment.yaml`, `cronjob.yaml`, `kustomization.yaml`), one replica, image
pinned to `ghcr.io/etzhayyim/kotodama:jukyu-mcp-query-1127e93592e-20260515170344-amd64`,
`RW_URL` from the `mitama-udf-pool-rw` secret, with the domain-adapter CronJob
schedules that `langgraph.json` mirrors. Read that tree at its own tip, not from
memory of this file.

## What is stale in the prose here

`CLAUDE.md` and `JUKYU_DESIGN.md` are worth reading for intent. These specific
statements in them are no longer true of this repository:

| Where | Says | Actually |
|---|---|---|
| `CLAUDE.md` App Identity | Manifest at `20-actors/jukyu/actor-manifest.jsonld` | not in this repo |
| `CLAUDE.md` App Identity | Design at `60-apps/etzhayyim-project-jukyu/JUKYU_DESIGN.md` | `./JUKYU_DESIGN.md` |
| `CLAUDE.md` Domain Adapters | eight domains ✅ with confidences 0.40–0.72 | describes the cluster; from a clone every data path is `store not configured` |
| `lg-clj/CLAUDE.md` Run | `cd 60-apps/etzhayyim-project-jukyu/lg-clj` | `cd lg-clj` |
| `lg-clj/CLAUDE.md` Run | 45 tests / 147 assertions | 50 tests / 160 assertions |
| `lg/CLAUDE.md` P1 DB schema | `30-graph/graph-schema/migrations/…` | not in this repo |
| `lg/CLAUDE.md` P1 Helm chart | `50-infra/vultr/lg-jukyu-pool/` | `etzhayyim/root` → `50-infra/k8s/lg-jukyu/` |
| `lg/CLAUDE.md` P2 UI cockpit | "SvelteKit" at `60-apps/…/App.svelte` | plain Svelte 5 + Vite (`index.html` + `src/main.ts`, no `@sveltejs/kit`) at `appview/jukyu-ui-jukyu001/svelte/src/App.svelte` |
| `README.edn` | name `com-etzhayyim-app-jukyu` | `cloud-itonami/jukyu` |
| `migration.edn` | `:source-path "60-apps/etzhayyim-project-jukyu"` | the monorepo layout it was extracted from |

The paths were correct where this code used to live. GitHub redirects repository
*names*; it does not redirect paths inside a tree, and extraction moved every one
of them.

## Toolchain note

`lg-clj` runs on babashka (`bb.edn`, `run_tests.clj`). The workspace retired `bb`
as a script host in ADR-2607173000 in favour of nbb, so do not copy this pattern
into new scripts. Nothing here has been migrated, and this README does not
propose migrating it — the suite is green under `bb` today.

## License

Apache License 2.0, with the etzhayyim Charter Compliance Rider v3.1 as stated in
[`NOTICE`](./NOTICE) (see item 7 above for where the rider text actually is).
