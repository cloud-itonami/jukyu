(ns cloud-itonami.jukyu.ui
  "View tree for the jukyu-ui appview UI of jukyu. Ported from the former
  appview/jukyu-ui-jukyu001/svelte/src/App.svelte (operational cockpit).
  Interactive controls (selects, watchlist buttons, tabs, action buttons,
  SVG node clicks) are hand-rolled hiccup dispatching to
  cloud-itonami.jukyu.actions. 2026-09-19: the appkit.core /
  kotoba-ui.core structural chrome was dropped to plain hiccup — ADR-
  2609111500 renamed those sources to .cljk and shadow-cljs 2.28.20 cannot
  resolve them, so every build requiring them failed. Restore the requires
  once .cljk resolution reaches shadow-cljs."
  (:require [cloud-itonami.jukyu.state :as state]
            [cloud-itonami.jukyu.actions :as actions]))

(def css-text
  "
.jk-cockpit { display: grid; grid-template-columns: 292px minmax(0, 1fr); min-height: 100vh; }
.jk-rail { background: #102033; color: #f8fafc; padding: 20px; display: flex; flex-direction: column; gap: 20px; }
.jk-brand { display: flex; gap: 12px; align-items: center; }
.jk-mark { width: 42px; height: 42px; display: grid; place-items: center; background: #f97316; border-radius: 8px; color: white; font-weight: 800; }
.jk-cockpit h1, .jk-cockpit h2, .jk-cockpit p { margin: 0; }
.jk-cockpit h1 { font-size: 20px; line-height: 1.2; }
.jk-cockpit h2 { font-size: 18px; line-height: 1.2; }
.jk-eyebrow, .jk-section-title { color: #64748b; font-size: 12px; font-weight: 700; text-transform: uppercase; }
.jk-rail .jk-eyebrow, .jk-rail .jk-section-title { color: #93a4b8; }
.jk-control-group { display: grid; gap: 8px; }
.jk-control-group label { font-size: 13px; font-weight: 700; }
.jk-control-group select { width: 100%; min-height: 44px; border: 1px solid rgba(255,255,255,0.22); border-radius: 8px; background: #f8fafc; color: #111827; padding: 0 12px; }
.jk-watchlist { display: grid; gap: 8px; }
.jk-watchlist button { border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.06); color: #f8fafc; border-radius: 8px; min-height: 48px; padding: 10px; display: flex; justify-content: space-between; align-items: center; text-align: left; cursor: pointer; }
.jk-watchlist button.active { border-color: #38bdf8; background: rgba(56,189,248,0.16); }
.jk-status-box { margin-top: auto; display: grid; gap: 8px; padding: 12px; border-radius: 8px; background: rgba(255,255,255,0.06); }
.jk-pulse { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.jk-pulse span { width: 9px; height: 9px; border-radius: 999px; background: #22c55e; }
.jk-pulse span.busy { background: #facc15; }
.jk-status-box small { color: #cbd5e1; overflow-wrap: anywhere; }
.jk-workspace { min-width: 0; padding: 18px; display: grid; gap: 16px; }
.jk-topbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.jk-tabs, .jk-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.jk-chip { border: 1px solid #d9e2ec; background: white; color: #334155; border-radius: 999px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
.jk-chip.active { border-color: #f97316; background: #ffedd5; color: #9a3412; font-weight: 700; }
.jk-btn { border: 1px solid #d9e2ec; background: white; color: #334155; border-radius: 8px; padding: 6px 12px; cursor: pointer; font-size: 13px; }
.jk-btn.solid { background: #f97316; border-color: #f97316; color: white; font-weight: 700; }
.jk-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.jk-metric { background: white; padding: 14px; border: 1px solid #d9e2ec; border-radius: 8px; }
.jk-metric.danger { border-color: #fecaca; background: #fff7f7; }
.jk-metric span, .jk-metric small { display: block; color: #64748b; font-size: 12px; }
.jk-metric strong { display: block; margin-top: 6px; color: #111827; font-size: 26px; line-height: 1; }
.jk-canvas-row { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 12px; align-items: stretch; }
.jk-panel { background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 14px; }
.jk-panel-heading { display: flex; justify-content: space-between; gap: 12px; align-items: start; margin-bottom: 8px; }
.jk-panel-heading.compact { align-items: center; }
.jk-graph-panel svg { width: 100%; min-height: 360px; background: linear-gradient(180deg, #f8fafc, #edf4fb); border: 1px solid #d9e2ec; border-radius: 8px; }
.jk-lane { stroke: #2563eb; stroke-linecap: round; opacity: 0.62; }
.jk-lane.risk-lane { stroke: #dc2626; opacity: 0.78; }
.jk-lane-label { fill: #334155; font-size: 13px; font-weight: 700; paint-order: stroke; stroke: white; stroke-width: 5px; }
.jk-node { cursor: pointer; outline: none; }
.jk-node circle { fill: white; stroke: #64748b; stroke-width: 3; }
.jk-node.surplus circle { stroke: #16a34a; fill: #f0fdf4; }
.jk-node.deficit circle { stroke: #dc2626; fill: #fef2f2; }
.jk-node.selected circle { stroke: #f97316; stroke-width: 5; }
.jk-node text { text-anchor: middle; fill: #111827; font-size: 14px; font-weight: 800; }
.jk-node .jk-node-code { font-size: 9px; font-weight: 700; fill: #475569; }
.jk-badge { border-radius: 999px; padding: 2px 10px; font-size: 11px; font-weight: 700; background: #e2e8f0; color: #334155; }
.jk-badge.error { background: #fee2e2; color: #991b1b; }
.jk-badge.warning { background: #fef9c3; color: #854d0e; }
.jk-badge.success { background: #dcfce7; color: #166534; }
.jk-badge.accent { background: #e0f2fe; color: #075985; }
.jk-inspector { display: grid; align-content: start; gap: 14px; }
.jk-risk-score { display: grid; grid-template-columns: 1fr auto auto; gap: 8px; align-items: center; padding: 12px; background: #f8fafc; border-radius: 8px; }
.jk-risk-score strong { font-size: 28px; }
.jk-pressure-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.jk-pressure-grid span { display: grid; gap: 4px; background: #f8fafc; border-radius: 8px; padding: 10px; color: #64748b; font-size: 12px; }
.jk-pressure-grid b { color: #111827; font-size: 18px; }
.jk-recommendation { color: #334155; font-size: 14px; line-height: 1.5; }
.jk-data-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.jk-table { display: grid; gap: 4px; }
.jk-tr { display: grid; grid-template-columns: 0.8fr 1fr 1fr 1fr; gap: 8px; align-items: center; min-height: 36px; padding: 8px; border-radius: 6px; background: #f8fafc; color: #334155; font-size: 13px; }
.jk-company-table .jk-tr { grid-template-columns: 1.7fr 0.7fr 0.8fr 0.7fr; }
.jk-tr.head { background: transparent; color: #64748b; font-weight: 800; }
.jk-tr.negative { background: #fef2f2; color: #991b1b; }
.jk-tr.clickable { width: 100%; border: 0; text-align: left; cursor: pointer; font: inherit; }
.jk-timeline { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.jk-event { display: grid; grid-template-columns: auto 1fr; gap: 4px 10px; align-items: start; background: white; border: 1px solid #d9e2ec; border-radius: 8px; padding: 12px; }
.jk-event i { grid-row: span 2; width: 10px; height: 10px; margin-top: 4px; border-radius: 999px; background: #f97316; }
.jk-event small { color: #64748b; line-height: 1.4; }
@media (max-width: 980px) {
  .jk-cockpit { grid-template-columns: 1fr; }
  .jk-canvas-row, .jk-data-grid, .jk-metrics, .jk-timeline { grid-template-columns: 1fr; }
  .jk-topbar { align-items: stretch; flex-direction: column; }
}
")

(defn- fmt-n [v]
  (.format (js/Intl.NumberFormat. "en-US" #js {:maximumFractionDigits 0}) v))

(defn- fmt-score [v] (.toFixed v 2))

(defn- risk-variant [score]
  (cond (>= score 0.8) "error"
        (>= score 0.65) "warning"
        :else "success"))

(defn- badge [value variant]
  [:span.jk-badge {:class variant} value])

(defn- select-control [{:keys [label id value on-change options]}]
  [:section.jk-control-group
   [:label {:for id} label]
   [:select {:id id :value value :on-change (fn [e] (on-change (.. e -target -value)))}
    options]])

(defn- rail [{:keys [selected-domain selected-country loading status last-run-id]}]
  (let [snap (get state/domains selected-domain (:naphtha state/domains))]
    [:aside.jk-rail
     [:div.jk-brand
      [:div.jk-mark "J"]
      [:div
       [:p.jk-eyebrow "jukyu.etzhayyim.com"]
       [:h1 "Global Balance"]]]
     [select-control
      {:label "Domain" :id "jk-domain" :value (name selected-domain)
       :on-change actions/select-domain!
       :options (doall (for [[k d] state/domains]
                         ^{:key k} [:option {:value (name k)} (:label d)]))}]
     [select-control
      {:label "Geography" :id "jk-country" :value selected-country
       :on-change actions/select-country!
       :options (into [[:option {:value "ALL"} "Global"]]
                      (map (fn [row] ^{:key (:country_code row)}
                             [:option {:value (:country_code row)} (:country_code row)])
                           (:balance snap)))}]
     [:section.jk-watchlist
      [:p.jk-section-title "Watchlist"]
      (doall (for [ex (:exposures @state/state)]
               ^{:key (:company_did ex)}
               [:button {:type "button"
                         :class (when (= selected-country (:country_code ex)) "active")
                         :on-click (fn [] (actions/select-country! (:country_code ex)))}
                [:span (:company_name ex)]
                [badge (fmt-score (:risk_score ex)) (risk-variant (:risk_score ex))]]))]
     [:section.jk-status-box
      [:p.jk-section-title "Agent Loop"]
      [:div.jk-pulse
       [:span {:class (when loading "busy")}]
       [:strong status]]
      [:small last-run-id]]]))

(defn- metric [cls label value note]
  [:div.jk-metric {:class cls}
   [:span label]
   [:strong value]
   [:small note]])

(defn- graph-svg [{:keys [s chain-rows node-layout selected-node]}]
  [:svg {:viewBox "0 0 880 540" :role "img"}
   [:defs
    [:marker {:id "jk-arrow" :markerHeight 10 :markerWidth 10 :orient "auto" :refX 8 :refY 3}
     [:path {:d "M0,0 L0,6 L9,3 z" :fill "#2563eb"}]]
    [:marker {:id "jk-arrow-risk" :markerHeight 10 :markerWidth 10 :orient "auto" :refX 8 :refY 3}
     [:path {:d "M0,0 L0,6 L9,3 z" :fill "#dc2626"}]]]
   (doall (for [lane chain-rows
                :let [src (some #(when (= (:id %) (:src_node_code lane)) %) node-layout)
                      dst (some #(when (= (:id %) (:dst_node_code lane)) %) node-layout)]
                :when (and src dst)]
            ^{:key (:edge_id lane)}
            [:g
             [:line {:class (str "jk-lane " (when (contains? #{"JP" "KR"} (:country dst)) "risk-lane"))
                     :x1 (:x src) :y1 (:y src) :x2 (:x dst) :y2 (:y dst)
                     :stroke-width (+ 2 (* (:dependency_weight lane) 5))
                     :marker-end (if (contains? #{"JP" "KR"} (:country dst)) "url(#jk-arrow-risk)" "url(#jk-arrow)")}]]))
   (doall (for [n node-layout
                :let [cls (str "jk-node "
                               (state/node-stress s n)
                               (when (= (:id n) selected-node) " selected"))]]
            ^{:key (:id n)}
            [:g {:class cls :tabIndex 0 :role "button"
                 :on-click (fn [] (actions/select-node! (:id n)))}
             [:circle {:cx (:x n) :cy (:y n) :r 32}]
             [:text {:x (:x n) :y (- (:y n) 4)} (:country n)]
             [:text.jk-node-code {:x (:x n) :y (+ (:y n) 15)} (:id n)]]))])

(defn- inspector [{:keys [selected-node exposure]}]
  [:div.jk-panel.jk-inspector
   [:p.jk-eyebrow "Inspector"]
   [:h2 selected-node]
   (if exposure
     [:div
      [:div.jk-risk-score
       [:span "Risk"]
       [:strong (fmt-score (:risk_score exposure))]
       [badge (:country_code exposure) (risk-variant (:risk_score exposure))]]
      [:div.jk-pressure-grid
       [:span "Supply " [:b (fmt-score (:supply_pressure exposure))]]
       [:span "Demand " [:b (fmt-score (:demand_pressure exposure))]]
       [:span "Downstream " [:b (fmt-score (:downstream_pressure exposure))]]
       [:span "Structural " [:b (fmt-score (:structural_pressure exposure))]]]
      [:p.jk-recommendation (:recommended_action exposure)]]
     [:p.jk-recommendation "No company exposure is attached to this node."])])

(defn- balance-table [{:keys [rows]}]
  [:div.jk-panel
   [:div.jk-panel-heading.compact [:h2 "Balance"] [badge (count rows) "default"]]
   [:div.jk-table
    [:div.jk-tr.head [:span "Country"] [:span "Supply"] [:span "Demand"] [:span "Balance"]]
    (doall (for [row rows]
             ^{:key (:country_code row)}
             [:div.jk-tr {:class (when (neg? (:balance_quantity row)) "negative")}
              [:span (:country_code row)]
              [:span (fmt-n (:supply_quantity row))]
              [:span (fmt-n (:demand_quantity row))]
              [:span (:balance_quantity row)]]))]])

(defn- company-table [{:keys [rows]}]
  [:div.jk-panel
   [:div.jk-panel-heading.compact [:h2 "Companies"] [badge (count rows) "default"]]
   [:div.jk-table.jk-company-table
    [:div.jk-tr.head [:span "Company"] [:span "Country"] [:span "Product"] [:span "Risk"]]
    (doall (for [row rows]
             ^{:key (:company_did row)}
             [:button.jk-tr.clickable {:type "button"
                                       :on-click (fn [] (actions/select-country! (:country_code row)))}
              [:span (:company_name row)]
              [:span (:country_code row)]
              [:span (:product_code row)]
              [:span (fmt-score (:risk_score row))]]))]])

(defn- timeline [{:keys [domain-snapshot]}]
  (let [[a b c] (:timeline domain-snapshot)]
    [:section.jk-timeline
     [:div.jk-event [:i] [:strong "Adapter"] [:small a]]
     [:div.jk-event [:i] [:strong "Pregel"] [:small b]]
     [:div.jk-event [:i] [:strong "Signal"] [:small c]]]))

(defn root []
  (let [s @state/state
        snapshot (state/domain-snapshot s (:selected-domain s))
        visible-balance (state/visible-balance s)
        visible-exposure (state/visible-exposure s)
        selected-exposure (state/selected-exposure s)
        deficit (state/total-deficit s)
        surplus (state/total-surplus s)
        critical (state/critical-count s)]
    [:div
     [:style css-text]
     [:main.jk-cockpit
      [rail s]
      [:section.jk-workspace
       [:header.jk-topbar
        [:div.jk-tabs {:aria-label "Views"}
         (doall (for [view ["Balance" "Chain" "Companies" "Signals"]]
                  ^{:key view}
                  [:button {:type "button"
                            :class (str "jk-chip " (when (= (:active-view s) view) "active"))
                            :on-click (fn [] (actions/select-view! view))}
                   view]))]
        [:div.jk-actions
         [:button {:type "button" :class "jk-btn" :on-click actions/normalize-domain!} "Adapter"]
         [:button {:type "button" :class "jk-btn" :on-click actions/drain-outbox!} "Outbox"]
         [:button {:type "button" :class "jk-btn solid" :on-click actions/run-equilibrium!} "Run Pregel"]]]
       [:section.jk-metrics
        (metric "" "Global surplus" (fmt-n surplus) (str (:label snapshot) " available"))
        (metric "danger" "Import deficit" (fmt-n deficit) (str (:label snapshot) " constrained"))
        (metric "" "Critical exposure" critical "company-country positions")
        (metric "" "Signals" (count (:signal-rows s)) "current run")]
       [:section.jk-canvas-row
        [:div.jk-panel.jk-graph-panel
         [:div.jk-panel-heading
          [:div
           [:p.jk-eyebrow "Supply-chain graph"]
           [:h2 (str (:label snapshot) " propagation")]]
          [badge "observed + inferred" "accent"]]
         [graph-svg {:s s
                     :chain-rows (:chain-rows s)
                     :node-layout (:node-layout s)
                     :selected-node (:selected-node s)}]]
        [inspector {:selected-node (:selected-node s) :exposure selected-exposure}]]
       [:section.jk-data-grid
        [balance-table {:rows visible-balance}]
        [company-table {:rows visible-exposure}]]
       [timeline {:domain-snapshot snapshot}]]]]))
