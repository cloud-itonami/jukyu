(ns cloud-itonami.jukyu.actions
  "Event handlers for the jukyu cockpit (ported from the former Svelte
  module functions). Pure state transitions plus the three async control
  actions (normalizeDomain / runEquilibrium / drainOutbox) which POST to
  the same /cron paths and only mutate status/rows — no DB I/O in the
  edge UI, matching the CLAUDE.md UX contract."
  (:require [reagent.core :as r]
            [cloud-itonami.jukyu.state :as state]))

(defn- swap!* [f & args]
  (apply swap! state/state f args))

(defn select-node! [id] (swap!* assoc :selected-node id))

(defn select-view! [view] (swap!* assoc :active-view view))

(defn select-domain! [value]
  (let [k (keyword value)
        snapshot (get state/domains k (get state/domains :naphtha))
        nodes (:nodes snapshot)]
    (swap!*
     (fn [s]
       (assoc s
              :selected-domain k
              :balance-rows (:balance snapshot)
              :chain-rows (:chain snapshot)
              :exposure-rows (:exposures snapshot)
              :node-layout nodes
              :selected-country "ALL"
              :selected-node (or (:id (nth nodes (- (count nodes) 2) nil))
                                 (:id (first nodes))
                                 "")
              :signal-rows []
              :status (str (:label snapshot) " fallback snapshot")
              :last-run-id (str (name k) "-seed"))))))

(defn select-country! [value]
  (swap!* assoc :selected-country value)
  (when-not (= value "ALL")
    (let [s @state/state
          n (some #(when (= (:country %) value) %) (:node-layout s))]
      (when n (select-node! (:id n))))))

(defn- fetch-ok [path init on-body on-error]
  (-> (js/fetch path (clj->js init))
      (.then (fn [resp]
               (if (.-ok resp)
                 (.json resp)
                 (js/Promise.reject (js/Error. (str path " " (.-status resp)))))))
      (.then (fn [body] (on-body (js->clj body :keywordize-keys true))))
      (.catch (fn [err] (on-error (.-message err))))))

(defn normalize-domain! []
  (let [snapshot (state/domain-snapshot @state/state (:selected-domain @state/state))
        path (:adapter-path snapshot)]
    (swap!* assoc :loading true :status (str "normalizing " (:label snapshot) " adapter"))
    (fetch-ok path {:method "POST"}
              (fn [body]
                (swap!* assoc :loading false
                        :status (str "adapter ok: " (or (:jukyuSupplyNodesTotal body)
                                                        (:supplyNodes body) 0) " nodes")))
              (fn [msg]
                (swap!* assoc :loading false :status (str "adapter unavailable: " msg))))))

(defn run-equilibrium! []
  (let [s @state/state
        country (:selected-country s)]
    (swap!* assoc :loading true :status "running equilibrium")
    (fetch-ok "/cron/equilibrium"
              {:method "POST"
               :headers {"content-type" "application/json"}
               :body (js/JSON.stringify
                      (clj->js {:domain (name (:selected-domain s))
                                :seedCountry (when-not (= country "ALL") country)
                                :riskThreshold 0.55
                                :maxBalanceRows 25
                                :maxChainRows 50
                                :maxExposureRows 25}))}
              (fn [body]
                (let [result (or (:result body) {})]
                  (swap!*
                   (fn [st]
                     (assoc st
                            :loading false
                            :balance-rows (if (seq (:balanceRows result))
                                            (:balanceRows result) (:balance-rows st))
                            :chain-rows (if (seq (:chainRows result))
                                          (:chainRows result) (:chain-rows st))
                            :exposure-rows (if (seq (:exposureRows result))
                                             (:exposureRows result) (:exposure-rows st))
                            :signal-rows (or (:signalRows result) (:signal-rows st))
                            :last-run-id (or (:runId result) (:last-run-id st))
                            :status (str "equilibrium ok: " (or (:signalsInserted result) 0) " signals"))))))
              (fn [msg]
                (swap!* assoc :loading false :status (str "live endpoint unavailable: " msg))))))

(defn drain-outbox! []
  (swap!* assoc :loading true :status "reading outbox")
  (fetch-ok "/cron/outbox-drain" {:method "POST"}
            (fn [body]
              (swap!* assoc :loading false
                      :status (str "outbox ok: " (or (:count body) 0) " pending")))
            (fn [msg]
              (swap!* assoc :loading false :status (str "outbox unavailable: " msg)))))
