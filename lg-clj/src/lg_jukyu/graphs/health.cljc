(ns lg-jukyu.graphs.health
  "jukyu `health` graph — store probe + liveness.

  NSID: com.etzhayyim.apps.jukyu.health
  Faithful clj port of `lg/lg_jukyu/graphs/health.py` (ADR-2606280030).
  Topology: START → check_rw → summarize → audit → END.

  DEVIATION: the Python `check_rw` opens a psycopg connection to RisingWave;
  here it is the injectable `store/*ping*` seam (substrate boundary). No
  RetryPolicy in langgraph-clj (the Python `RetryPolicy(max_attempts=2)` on
  check_rw has no clj analogue — noted)."
  (:require [langgraph.graph :as g]
            [lg-jukyu.store :as store]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]))

(defn node-check-rw [_state]
  (let [res (store/*ping*)]
    (if (:rw_ok res)
      {:rw_ok true :rw_latency_ms (:rw_latency_ms res)}
      {:rw_ok false :error (or (:error res) "rw down")})))

(defn node-summarize [state]
  {:ok (boolean (:rw_ok state)) :server_now (util/now-iso)})

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.health.check"
                     :object-id (str "health:" (quot (System/currentTimeMillis) 1000))
                     :object-type "jukyu.health"
                     :attributes {:ok (:ok state false) :rwOk (:rw_ok state false)}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :check_rw node-check-rw)
      (g/add-node :summarize node-summarize)
      (g/add-node :audit node-audit)
      (g/add-edge :check_rw :summarize)
      (g/add-edge :summarize :audit)
      (g/set-entry-point :check_rw)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
