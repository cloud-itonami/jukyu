(ns lg-jukyu.graphs.upsert-signal
  "jukyu `upsertSignal` graph — write a notification signal to the outbox.

  NSID: com.etzhayyim.apps.jukyu.upsertSignal
  Faithful clj port of `upsert_signal.py`. Topology: START → write → audit → END.
  Validates target_company_did, derives signal_id + severity (from risk if unset),
  then writes via the `store/*write-signal*` seam (delete-then-insert in python)."
  (:require [langgraph.graph :as g]
            [clojure.string :as str]
            [lg-jukyu.store :as store]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util])
  #?(:clj (:import [java.time ZonedDateTime ZoneOffset]
                   [java.time.format DateTimeFormatter])))

(defn- yyyymmdd []
  #?(:clj (.format (DateTimeFormatter/ofPattern "yyyyMMdd")
                   (ZonedDateTime/now ZoneOffset/UTC))
     :cljs (subs (str/replace (util/now-iso) #"-" "") 0 8)))

(defn- rand-hex [n]
  (apply str (repeatedly n #(rand-nth "0123456789abcdef"))))

(defn node-write [state]
  (let [company-did (str/trim (or (:target_company_did state) ""))]
    (if (str/blank? company-did)
      {:ok false :error "target_company_did is required"}
      (let [risk      (util/as-float (:risk_score state) 0)
            conf      (util/as-float (:confidence state) 0)
            signal-id (or (:signal_id state)
                          (str "jukyu-signal:" (yyyymmdd) ":"
                               (subs company-did 0 (min 30 (count company-did)))
                               ":" (rand-hex 8)))
            severity  (or (:severity state) (util/severity risk))
            vertex-id (str "at://jukyu001.etzhayyim.com/com.etzhayyim.apps.jukyu.notificationSignal/"
                           (rand-hex 12))
            record    {:vertex_id vertex-id :signal_id signal-id
                       :target_company_did company-did :run_id "manual"
                       :risk_score risk :confidence conf :severity severity
                       :domain (or (:domain state) "global")
                       :recommended_action (or (:recommended_action state) "")
                       :title (:title state) :body (:body state)
                       :notification_status "pending"}
            res       (store/*write-signal* record)]
        (if (:ok res)
          {:ok true :signal_id signal-id}
          {:ok false :error (or (:error res) "write failed")})))))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.upsertSignal"
                     :object-id (or (:signal_id state) "unknown")
                     :object-type "jukyu.notificationSignal"
                     :attributes {:ok (:ok state false)
                                  :companyDid (:target_company_did state)}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :write node-write)
      (g/add-node :audit node-audit)
      (g/add-edge :write :audit)
      (g/set-entry-point :write)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
