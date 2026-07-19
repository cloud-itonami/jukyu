(ns lg-jukyu.graphs.run-stress-propagation
  "jukyu `runStressPropagation` graph — the Pregel equilibrium propagation
  (graph jukyu_global_equilibrium_v1).

  NSID: com.etzhayyim.apps.jukyu.runStressPropagation
  Faithful clj port of `run_stress_propagation.py`. Topology (9 nodes):
    init_run → read_balance → read_chain → parse_scenario → propagate →
    write_signals → enrich_signals → read_outbox → audit

  The `propagate` node is the VERIFIABLE compute core — delegated to
  `lg-jukyu.pregel/propagate-full` (risk weighting + confidence formula + halting
  ported exactly). DB reads/writes are `store/*` seams; LLM legs (parse_scenario,
  enrich_signals) are `llm/*chat*`. No RetryPolicy in langgraph-clj (noted)."
  (:require [langgraph.graph :as g]
            [lg-jukyu.store :as store]
            [lg-jukyu.llm :as llm]
            [lg-jukyu.pregel :as pregel]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]
            [lg-jukyu.graphs.extract-shocks :as es])
  #?(:clj (:import [java.time ZonedDateTime ZoneOffset]
                   [java.time.format DateTimeFormatter])))

(def ^:dynamic *enrich-max*
  "Host-supplied cap for LLM enrichment work per run."
  10)

(defn- ts-compact []
  #?(:clj (.format (DateTimeFormatter/ofPattern "yyyyMMdd'T'HHmmss'Z'")
                   (ZonedDateTime/now ZoneOffset/UTC))
     :cljs (clojure.string/replace (util/now-iso) #"[:-]" "")))

(defn node-init-run [state]
  {:run_id (str "jukyu.global." (or (:domain state) "all") "." (ts-compact))
   :superstep 0 :converged false
   :shock_seeds (or (:shock_seeds state) {})
   :max_iterations (min 8 (util/as-int (:max_iterations state) 8))})

(defn node-read-balance [state]
  (let [res (store/*read-balance-rows* (:domain state))]
    (cond-> {:balance_rows (or (:rows res) [])}
      (:error res) (assoc :error (:error res)))))

(defn node-read-chain [state]
  (let [res (store/*read-chain-rows* (:domain state))]
    (cond-> {:supply_nodes (or (:nodes res) []) :supply_edges (or (:edges res) [])}
      (:error res) (assoc :error (:error res)))))

(defn node-parse-scenario [state]
  (let [scenario (:scenario_text state)
        with-llm (:with_llm state false)
        seeds (into {} (:shock_seeds state {}))]
    (if (or (not scenario) (clojure.string/blank? (str scenario)) (not with-llm))
      {:parsed_shocks []}
      (let [res (llm/chat {:model llm/extraction-model
                             :system "You are a commodity supply-chain analyst. Output only valid JSON."
                             :user (str "Extract supply-demand shock events from the following text.\n"
                                        "Return JSON array with fields: shock_type, domain, country_code, "
                                        "severity (0-1), duration_days, description.\n\nText:\n" scenario)
                             :max-tokens 1024 :temperature 0.1})]
        (if (map? res)
          {:parsed_shocks []} ;; non-fatal (python warns + returns [])
          (let [shocks (es/parse-json-array res)
                seeds' (reduce (fn [m shock]
                                 (let [k (str (get shock :domain "") "." (get shock :country_code ""))]
                                   (assoc m k (max (get m k 0) (util/as-float (get shock :severity 0) 0)))))
                               seeds shocks)]
            {:parsed_shocks shocks :shock_seeds seeds'}))))))

(defn node-propagate [state]
  (pregel/propagate-full state))

(defn node-write-signals [state]
  (let [exposures (or (:company_exposures state) [])
        run-id (:run_id state)]
    (if (empty? exposures)
      {:signals_written 0}
      (let [res (store/*write-signals-batch* run-id (or (:domain state) "global") exposures)]
        (cond-> {:signals_written (:written res 0)}
          (:error res) (assoc :error (:error res)))))))

(defn node-enrich-signals [state]
  (if-not (:with_llm state)
    {:signals_enriched 0}
    (let [domain (or (:domain state) "global")
          candidates (take *enrich-max* (or (:company_exposures state) []))]
      (loop [cs candidates enriched 0]
        (if-let [ce (first cs)]
          (let [risk (util/as-float (:riskScore ce) 0)]
            (if (< risk 0.4)
              (recur (rest cs) enriched)
              (let [res (llm/chat
                         {:model llm/narrative-model
                          :system "You are a supply-chain risk analyst. Output only valid JSON."
                          :user (str "Write a brief executive signal for a supply-chain risk alert.\n"
                                     "Company: " (or (:companyDid ce) "?") "\nDomain: " domain
                                     "\nRisk score: " (format "%.2f" (double risk))
                                     " (supply=" (format "%.2f" (double (:supplyPressure ce 0)))
                                     ", demand=" (format "%.2f" (double (:demandPressure ce 0))) ")\n\n"
                                     "Output JSON with fields: title (< 60 chars), body (< 200 chars), "
                                     "recommended_action (< 100 chars).")
                          :max-tokens 256 :temperature 0.3})]
                (if (map? res) ;; error → python aborts the loop (non-fatal)
                  {:signals_enriched enriched}
                  (recur (rest cs) (inc enriched))))))
          {:signals_enriched enriched})))))

(defn node-read-outbox [state]
  (let [res (store/*read-run-outbox* (:run_id state))]
    {:outbox (or (:rows res) [])}))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.runStressPropagation"
                     :object-id (or (:run_id state) "unknown")
                     :object-type "jukyu.pregelRun"
                     :attributes {:superstep (:superstep state 0)
                                  :converged (:converged state false)
                                  :signalsWritten (:signals_written state 0)
                                  :companyCount (count (:company_exposures state []))}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :init_run node-init-run)
      (g/add-node :read_balance node-read-balance)
      (g/add-node :read_chain node-read-chain)
      (g/add-node :parse_scenario node-parse-scenario)
      (g/add-node :propagate node-propagate)
      (g/add-node :write_signals node-write-signals)
      (g/add-node :enrich_signals node-enrich-signals)
      (g/add-node :read_outbox node-read-outbox)
      (g/add-node :audit node-audit)
      (g/add-edge :init_run :read_balance)
      (g/add-edge :read_balance :read_chain)
      (g/add-edge :read_chain :parse_scenario)
      (g/add-edge :parse_scenario :propagate)
      (g/add-edge :propagate :write_signals)
      (g/add-edge :write_signals :enrich_signals)
      (g/add-edge :enrich_signals :read_outbox)
      (g/add-edge :read_outbox :audit)
      (g/set-entry-point :init_run)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
