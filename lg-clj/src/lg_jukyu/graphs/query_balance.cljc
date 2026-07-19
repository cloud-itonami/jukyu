(ns lg-jukyu.graphs.query-balance
  "jukyu `queryBalance` graph — read mv_jukyu_global_balance.

  NSID: com.etzhayyim.apps.jukyu.queryBalance
  Faithful clj port of `query_balance.py`. Topology: START → query → audit → END.
  Filters: domain, country_code, product_family; limit clamped to [1,500].
  DEVIATION: psycopg → `store/*query-balance*` seam (substrate boundary)."
  (:require [langgraph.graph :as g]
            [lg-jukyu.store :as store]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]))

(defn node-query [state]
  (let [limit (util/clamp (util/as-int (:limit state) 100) 1 500)
        res   (store/*query-balance* {:domain (:domain state)
                                      :country_code (:country_code state)
                                      :product_family (:product_family state)
                                      :limit limit})]
    (if (:error res)
      {:error (:error res) :rows []}
      (let [rows (mapv (fn [r]
                         {:domain (:domain r)
                          :countryCode (:countryCode r)
                          :productFamily (:productFamily r)
                          :supplyQuantity (util/as-float (:supplyQuantity r) 0)
                          :demandQuantity (util/as-float (:demandQuantity r) 0)
                          :inventoryQuantity (util/as-float (:inventoryQuantity r) 0)
                          :balanceQuantity (util/as-float (:balanceQuantity r) 0)
                          :confidence (util/as-float (:confidence r) 0)
                          :latestObservedAt (str (:latestObservedAt r ""))
                          :observationCount (util/as-int (:observationCount r) 0)})
                       (:rows res))]
        {:rows rows :total (count rows)}))))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.queryBalance"
                     :object-id (str "queryBalance:" (quot (System/currentTimeMillis) 1000))
                     :object-type "jukyu.balance"
                     :attributes {:returned (:total state 0) :domain (:domain state)}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :query node-query)
      (g/add-node :audit node-audit)
      (g/add-edge :query :audit)
      (g/set-entry-point :query)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
