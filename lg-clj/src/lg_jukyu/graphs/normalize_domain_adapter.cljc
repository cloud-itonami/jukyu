(ns lg-jukyu.graphs.normalize-domain-adapter
  "jukyu `normalizeDomainAdapter` graph — normalize one domain's source tables
  into vertex_jukyu_*/edge_jukyu_*.

  NSID: com.etzhayyim.apps.jukyu.normalizeDomainAdapter
  Faithful clj port of `normalize_domain_adapter.py`. Topology: START → normalize
  → audit → END. The python per-domain SQL projections (naphtha / crude_oil /
  semiconductor / generic energy·food·metals·logistics / transport) are the
  load-bearing DB-write logic; the substrate boundary forbids RisingWave, so the
  whole projection is the injectable `store/*normalize-domain*` seam (domain →
  upsert counts). The domain→confidence map + validation are preserved here.
  DEVIATION: the per-table SQL upserts move into the (kotoba-Datom-log) store impl."
  (:require [langgraph.graph :as g]
            [clojure.string :as str]
            [lg-jukyu.store :as store]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]))

(def domain-confidence
  {"naphtha" 0.72 "crude_oil" 0.60 "energy" 0.45 "food" 0.40
   "metals" 0.40 "logistics" 0.42 "transport" 0.56})

(def supported-domains
  #{"naphtha" "crude_oil" "semiconductor" "energy" "food" "metals" "logistics" "transport"})

(defn node-normalize [state]
  (let [domain (str/lower-case (str/trim (or (:domain state) "")))]
    (cond
      (str/blank? domain) {:error "domain is required"}
      (not (contains? supported-domains domain))
      {:upserted_nodes 0 :upserted_edges 0 :upserted_balances 0
       :error (str "unsupported domain: " domain)}
      :else
      (let [confidence (get domain-confidence domain 0.40)
            res (store/*normalize-domain* domain confidence)]
        (merge {:upserted_nodes (:upserted_nodes res 0)
                :upserted_edges (:upserted_edges res 0)
                :upserted_balances (:upserted_balances res 0)}
               (when (:error res) {:error (:error res)})
               {:freshness_at (util/now-iso)})))))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.normalizeDomainAdapter"
                     :object-id (str "normalize:" (or (:domain state) "?") ":"
                                     (quot (System/currentTimeMillis) 1000))
                     :object-type "jukyu.domainAdapter"
                     :attributes {:domain (:domain state)
                                  :upsertedNodes (:upserted_nodes state 0)
                                  :upsertedEdges (:upserted_edges state 0)
                                  :upsertedBalances (:upserted_balances state 0)}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :normalize node-normalize)
      (g/add-node :audit node-audit)
      (g/add-edge :normalize :audit)
      (g/set-entry-point :normalize)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
