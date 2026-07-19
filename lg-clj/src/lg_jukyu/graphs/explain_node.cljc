(ns lg-jukyu.graphs.explain-node
  "jukyu `explainNode` graph — node + upstream chain (50) + balance (10).

  NSID: com.etzhayyim.apps.jukyu.explainNode
  Faithful clj port of `explain_node.py`. Topology: START → fetch → audit → END.
  Required: node_code. The composite read (node + chain + balance + operator
  company-exposure) is hoisted to the `store/*explain-fetch*` seam; the validation
  guards (missing node_code, node-not-found) are preserved in the node."
  (:require [langgraph.graph :as g]
            [clojure.string :as str]
            [lg-jukyu.store :as store]
            [lg-jukyu.audit :as audit]))

(defn node-fetch [state]
  (let [node-code (str/trim (or (:node_code state) ""))]
    (cond
      (str/blank? node-code) {:error "node_code is required"}
      :else
      (let [res (store/*explain-fetch* node-code)]
        (cond
          (nil? res) {:error (str "node not found: " node-code) :chain [] :balance []}
          (:error res) {:error (:error res) :chain [] :balance []}
          (nil? (:node res)) {:error (str "node not found: " node-code) :chain [] :balance []}
          :else {:node (:node res)
                 :chain (or (:chain res) [])
                 :balance (or (:balance res) [])
                 :company_exposure (:company_exposure res)})))))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.explainNode"
                     :object-id (or (:node_code state) "unknown")
                     :object-type "jukyu.supplyNode"
                     :attributes {:chainLen (count (:chain state []))
                                  :balanceLen (count (:balance state []))}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :fetch node-fetch)
      (g/add-node :audit node-audit)
      (g/add-edge :fetch :audit)
      (g/set-entry-point :fetch)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
