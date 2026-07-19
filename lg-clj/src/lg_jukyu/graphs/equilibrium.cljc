(ns lg-jukyu.graphs.equilibrium
  "jukyu resident 15-min equilibrium loop graph (cron `*/15 * * * *`, with_llm=false).

  Faithful clj port of `equilibrium.py`. Topology (7 nodes):
    init → read_balance → read_chain → propagate → write_signals →
    read_outbox_count → audit

  Runs the full Pregel cycle for ALL domains without LLM enrichment. The
  `propagate` node delegates to `lg-jukyu.pregel/propagate-equil` (node-confidence
  variant). DB I/O via `store/*` seams. No XRPC surface — cron-triggered only."
  (:require [langgraph.graph :as g]
            [lg-jukyu.store :as store]
            [lg-jukyu.pregel :as pregel]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]))

(defn node-init [state]
  {:run_id (str "jukyu.equil." (util/now-iso))
   :superstep 0 :converged false :shock_seeds {} :max_iterations 8
   :with_llm (boolean (:with_llm state false))})

(defn node-read-balance [_state]
  (let [res (store/*read-balance-rows* nil)]
    {:balance_rows (or (:rows res) [])}))

(defn node-read-chain [_state]
  (let [res (store/*read-chain-rows* nil)]
    {:supply_nodes (or (:nodes res) []) :supply_edges (or (:edges res) [])}))

(defn node-propagate [state]
  (pregel/propagate-equil state))

(defn node-write-signals [state]
  (let [exposures (or (:company_exposures state) [])
        res (store/*write-signals-batch* (:run_id state) "global" exposures)]
    {:signals_written (:written res 0)}))

(defn node-read-outbox-count [_state]
  {:outbox_count (store/*outbox-pending-count*)})

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.equilibrium.run"
                     :object-id (or (:run_id state) "unknown")
                     :object-type "jukyu.pregelRun"
                     :attributes {:superstep (:superstep state 0)
                                  :converged (:converged state false)
                                  :signalsWritten (:signals_written state 0)
                                  :outboxCount (:outbox_count state 0)
                                  :companyCount (count (:company_exposures state []))}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :init node-init)
      (g/add-node :read_balance node-read-balance)
      (g/add-node :read_chain node-read-chain)
      (g/add-node :propagate node-propagate)
      (g/add-node :write_signals node-write-signals)
      (g/add-node :read_outbox_count node-read-outbox-count)
      (g/add-node :audit node-audit)
      (g/add-edge :init :read_balance)
      (g/add-edge :read_balance :read_chain)
      (g/add-edge :read_chain :propagate)
      (g/add-edge :propagate :write_signals)
      (g/add-edge :write_signals :read_outbox_count)
      (g/add-edge :read_outbox_count :audit)
      (g/set-entry-point :init)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
