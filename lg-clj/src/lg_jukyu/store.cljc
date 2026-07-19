(ns lg-jukyu.store
  "Injectable STORE SEAM for the jukyu clj port (ADR-2606280030).

  The Python graphs talk to RisingWave over psycopg (`mv_jukyu_*` /
  `vertex_jukyu_*` / `edge_jukyu_*`). The repo substrate boundary FORBIDS
  RisingWave (state = kotoba Datom log), so every DB read/write is hoisted here
  as a dynamic var. The default impls return `{:error \"store not configured\"}`
  / empty — exact parity with the Python `RW_URL`-unset guard (every graph
  returns empty rows + an error string when no store is wired). A kotoba-Datom-log
  backend can be bound at the deployment layer; tests rebind to in-memory stubs.

  COEXISTENCE: the live data path stays the FastAPI/RisingWave pod under `lg/`;
  these seams are the clj twin's substrate-clean replacement, not yet wired live."
  (:require [clojure.string :as str]))

(def ^:const not-configured "store not configured")

;; ── health ──────────────────────────────────────────────────────────────────
(def ^:dynamic *ping*
  "() -> {:rw_ok bool :rw_latency_ms n} | {:rw_ok false :error ...}."
  (fn [] {:rw_ok false :error not-configured}))

;; ── reads (XRPC query graphs) ─────────────────────────────────────────────────
(def ^:dynamic *query-balance*
  "(filters) -> {:rows [row..]} | {:error ...}. filters: {:domain :country_code
  :product_family :limit}. Rows are camelCase balance maps."
  (fn [_filters] {:rows [] :error not-configured}))

(def ^:dynamic *query-chain*
  "(filters) -> {:rows [edge-row..]} | {:error ...}. Each edge-row carries
  embedded src/dst node fields (mirrors mv_jukyu_supply_chain_trace)."
  (fn [_filters] {:rows [] :error not-configured}))

(def ^:dynamic *query-exposure*
  "(filters) -> {:rows [company-row..]} | {:error ...}."
  (fn [_filters] {:rows [] :error not-configured}))

(def ^:dynamic *explain-fetch*
  "(node-code) -> {:node {..} :chain [..] :balance [..] :company_exposure {..}|nil}
  | {:error ...} | nil (node not found)."
  (fn [_node-code] {:error not-configured}))

;; ── writes ────────────────────────────────────────────────────────────────────
(def ^:dynamic *write-signal*
  "(record) -> {:ok true} | {:error ...}."
  (fn [_record] {:ok false :error not-configured}))

(def ^:dynamic *read-outbox*
  "(filters) -> {:rows [outbox-row..]} | {:error ...}. filters: {:domain :limit}."
  (fn [_filters] {:rows [] :error not-configured}))

;; ── notify_company ────────────────────────────────────────────────────────────
(def ^:dynamic *load-signal*
  "(signal-id) -> {:row {..}} | nil (not found) | {:error ...}."
  (fn [_signal-id] {:error not-configured}))

(def ^:dynamic *dispatch-signal*
  "(payload) -> {:ok bool}. Default: not dispatched."
  (fn [_payload] {:ok false}))

(def ^:dynamic *update-status*
  "(signal-id status) -> any. Default no-op."
  (fn [_signal-id _status] nil))

;; ── normalize_domain_adapter ──────────────────────────────────────────────────
(def ^:dynamic *normalize-domain*
  "(domain confidence) -> {:upserted_nodes n :upserted_edges n :upserted_balances n}
  | {:error ...}."
  (fn [_domain _confidence] {:upserted_nodes 0 :upserted_edges 0 :upserted_balances 0
                             :error not-configured}))

;; ── pregel reads/writes (run_stress_propagation + equilibrium) ────────────────
(def ^:dynamic *read-balance-rows*
  "(domain) -> {:rows [balance-row..]} | {:error ...}."
  (fn [_domain] {:rows []}))

(def ^:dynamic *read-chain-rows*
  "(domain) -> {:nodes [node..] :edges [edge..]} | {:error ...}."
  (fn [_domain] {:nodes [] :edges []}))

(def ^:dynamic *write-signals-batch*
  "(run-id domain exposures) -> {:written n} | {:written n :error ...}."
  (fn [_run-id _domain _exposures] {:written 0}))

(def ^:dynamic *read-run-outbox*
  "(run-id) -> {:rows [outbox-row..]}."
  (fn [_run-id] {:rows []}))

(def ^:dynamic *outbox-pending-count*
  "() -> int."
  (fn [] 0))

(defn blank? [s] (or (nil? s) (str/blank? (str s))))
