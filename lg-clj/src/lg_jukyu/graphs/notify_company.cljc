(ns lg-jukyu.graphs.notify-company
  "jukyu `notifyCompany` graph — dispatch a signal to a target company actor.

  NSID: com.etzhayyim.apps.jukyu.notifyCompany
  Faithful clj port of `notify_company.py`. Topology: START → load_signal →
  dispatch → audit → END. load_signal reads the stored signal, dispatch POSTs to
  the BPMN dispatcher then updates delivery status. DEVIATIONS: psycopg →
  `store/*load-signal*`/`*update-status*`; httpx → `store/*dispatch-signal*`."
  (:require [langgraph.graph :as g]
            [clojure.string :as str]
            [lg-jukyu.store :as store]
            [lg-jukyu.audit :as audit]))

(def app-did audit/app-did)

(defn node-load-signal [state]
  (let [signal-id (str/trim (or (:signal_id state) ""))]
    (if (str/blank? signal-id)
      {:ok false :error "signal_id is required"}
      (let [res (store/*load-signal* signal-id)]
        (cond
          (:error res) {:ok false :error (:error res)}
          (or (nil? res) (nil? (:row res))) {:ok false :error (str "signal not found: " signal-id)}
          :else (let [row (:row res)]
                  {:signal_id (or (:signal_id row) signal-id)
                   :target_company_did (or (:target_company_did row)
                                           (:target_company_did state) "")
                   :_loaded_signal {:riskScore (:risk_score row) :confidence (:confidence row)
                                    :severity (:severity row) :domain (:domain row)
                                    :recommendedAction (:recommended_action row)
                                    :title (:title row) :body (:body row)}}))))))

(defn node-dispatch [state]
  (let [signal-id (or (:signal_id state) "")
        company-did (or (:target_company_did state) "")
        channel (or (:channel state) "mcp")
        trace-id (str "jukyu-notify:" (subs signal-id 0 (min 20 (count signal-id)))
                      ":" (quot (System/currentTimeMillis) 1000))
        payload {:actor app-did :activity "jukyu.notifyCompany"
                 :objectId signal-id :objectType "jukyu.notificationSignal"
                 :attributes {:targetCompanyDid company-did :channel channel
                              :traceId trace-id :signal (or (:_loaded_signal state) {})}}
        disp (store/*dispatch-signal* payload)
        ok (boolean (:ok disp))
        new-status (if ok "dispatched" "dispatch_failed")]
    (store/*update-status* signal-id new-status)
    {:ok ok :delivery_status new-status :trace_id trace-id}))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.notifyCompany"
                     :object-id (or (:signal_id state) "unknown")
                     :object-type "jukyu.notificationSignal"
                     :attributes {:ok (:ok state false) :traceId (:trace_id state)
                                  :companyDid (:target_company_did state)}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :load_signal node-load-signal)
      (g/add-node :dispatch node-dispatch)
      (g/add-node :audit node-audit)
      (g/add-edge :load_signal :dispatch)
      (g/add-edge :dispatch :audit)
      (g/set-entry-point :load_signal)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
