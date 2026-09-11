(ns lg-jukyu.graphs.query-supply-chain
  "jukyu `querySupplyChain` graph — read mv_jukyu_supply_chain_trace.

  NSID: com.etzhayyim.apps.jukyu.querySupplyChain
  Faithful clj port of `query_supply_chain.py`. Topology: START → query_nodes →
  audit → END. Filters: domain, country_code/seed_country, product_family,
  node_code; limit clamped to [1,1000]. Unique nodes extracted from each edge's
  embedded src/dst fields (mirrors the python set-dedup).
  DEVIATION: psycopg → `store/*query-chain*` seam."
  (:require [langgraph.graph :as g]
            [lg-jukyu.store :as store]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]))

(defn- extract-nodes [rows]
  (loop [rows rows seen #{} acc []]
    (if-let [r (first rows)]
      (let [pairs [[(:src_vid r) (:src_node_code r) (:src_node_kind r) (:src_name r)
                    (:src_country_code r) (:src_operator_did r)]
                   [(:dst_vid r) (:dst_node_code r) (:dst_node_kind r) (:dst_name r)
                    (:dst_country_code r) (:dst_operator_did r)]]
            [seen' acc'] (reduce (fn [[s a] [vid code kind name cc op]]
                                   (if (contains? s vid)
                                     [s a]
                                     [(conj s vid)
                                      (conj a {:nodeId vid :nodeCode code :nodeKind kind
                                               :displayName (or name "") :countryCode (or cc "")
                                               :operatorDid (or op "")})]))
                                 [seen acc] pairs)]
        (recur (rest rows) seen' acc'))
      acc)))

(defn node-query [state]
  (let [limit (util/clamp (util/as-int (:limit state) 200) 1 1000)
        res   (store/*query-chain* {:domain (:domain state)
                                    :country_code (or (:country_code state) (:seed_country state))
                                    :product_family (:product_family state)
                                    :node_code (:node_code state)
                                    :limit limit})]
    (if (:error res)
      {:error (:error res) :nodes [] :edges []}
      (let [rows  (:rows res)
            nodes (extract-nodes rows)
            edges (mapv (fn [r]
                          {:edgeId (:edge_id r) :domain (:domain r) :relationship (:relationship r)
                           :srcVid (:src_vid r) :dstVid (:dst_vid r)
                           :capacityQuantity (util/as-float (:capacity_quantity r) 0)
                           :dependencyWeight (util/as-float (:dependency_weight r) 0)
                           :confidence (util/as-float (:confidence r) 0)})
                        rows)]
        {:nodes nodes :edges edges :total_nodes (count nodes) :total_edges (count edges)}))))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.querySupplyChain"
                     :object-id (str "querySupplyChain:" (quot (System/currentTimeMillis) 1000))
                     :object-type "jukyu.supplyChain"
                     :attributes {:totalNodes (:total_nodes state 0)
                                  :totalEdges (:total_edges state 0)
                                  :domain (:domain state)}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :query_nodes node-query)
      (g/add-node :audit node-audit)
      (g/add-edge :query_nodes :audit)
      (g/set-entry-point :query_nodes)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
