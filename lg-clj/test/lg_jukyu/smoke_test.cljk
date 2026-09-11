(ns lg-jukyu.smoke-test
  "Smoke tests for the lg-jukyu clj port — clojure.test analogue of the Python
  `tests/test_smoke.py`, plus node-behaviour + Pregel-core tests the original
  could not run offline (DB/LLM are injectable here, so the propagate compute,
  validation guards and transforms verify under bb with stubs)."
  (:require [clojure.test :refer [deftest is testing]]
            [langgraph.graph :as g]
            [lg-jukyu.server :as server]
            [lg-jukyu.cron :as cron]
            [lg-jukyu.store :as store]
            [lg-jukyu.llm :as llm]
            [lg-jukyu.util :as util]
            [lg-jukyu.pregel :as pregel]
            [lg-jukyu.graphs.health :as health]
            [lg-jukyu.graphs.query-balance :as qb]
            [lg-jukyu.graphs.query-supply-chain :as qsc]
            [lg-jukyu.graphs.rank-company-exposure :as rce]
            [lg-jukyu.graphs.explain-node :as en]
            [lg-jukyu.graphs.upsert-signal :as us]
            [lg-jukyu.graphs.extract-shocks :as es]
            [lg-jukyu.graphs.export-brief :as eb]
            [lg-jukyu.graphs.notify-company :as nc]
            [lg-jukyu.graphs.normalize-domain-adapter :as nda]
            [lg-jukyu.graphs.run-stress-propagation :as rsp]
            [lg-jukyu.graphs.equilibrium :as equil]))

(def expected-graphs
  #{"health" "query_balance" "query_supply_chain" "rank_company_exposure"
    "explain_node" "run_stress_propagation" "upsert_signal" "export_brief"
    "notify_company" "normalize_domain_adapter" "extract_shocks" "equilibrium"})

(def expected-nsids
  #{"com.etzhayyim.apps.jukyu.health"
    "com.etzhayyim.apps.jukyu.queryBalance"
    "com.etzhayyim.apps.jukyu.querySupplyChain"
    "com.etzhayyim.apps.jukyu.rankCompanyExposure"
    "com.etzhayyim.apps.jukyu.explainNode"
    "com.etzhayyim.apps.jukyu.runStressPropagation"
    "com.etzhayyim.apps.jukyu.upsertSignal"
    "com.etzhayyim.apps.jukyu.exportBrief"
    "com.etzhayyim.apps.jukyu.notifyCompany"
    "com.etzhayyim.apps.jukyu.normalizeDomainAdapter"
    "com.etzhayyim.apps.jukyu.extractShocks"})

;; ── server registry parity (mirrors test_smoke.py) ──────────────────────────

(deftest graphs-match-expected-set
  (is (= expected-graphs (set (keys server/GRAPHS)))))

(deftest nsid-map-coverage
  (is (= expected-nsids (set (keys server/NSID-MAP)))))

(deftest nsid-map-references-known-graphs
  (doseq [[nsid aid] server/NSID-MAP]
    (is (contains? server/GRAPHS aid) (str nsid " → " aid " not in GRAPHS"))))

(deftest all-graphs-non-nil
  (doseq [[nm graph] server/GRAPHS]
    (is (some? graph) (str "GRAPHS[" nm "] nil"))))

(deftest all-graphs-invocable
  (doseq [[nm graph] server/GRAPHS]
    (is (map? (g/invoke graph {})) (str nm " did not return a map"))))

;; ── dispatch surface (/ok, /runs, /xrpc) ────────────────────────────────────

(deftest health-endpoint
  (let [r (server/health)]
    (is (= 200 (:status r)))
    (is (true? (get-in r [:body :ok])))
    (is (= expected-graphs (set (get-in r [:body :graphs]))))
    (is (= "0.1.0" (get-in r [:body :version])))))

(deftest unknown-assistant-404
  (is (= 404 (:status (server/dispatch-run {:assistant_id "nope" :input {}})))))

(deftest unknown-nsid-404
  (is (= 404 (:status (server/dispatch-xrpc "com.etzhayyim.apps.jukyu.unknownMethod" {})))))

(deftest api-key-guard
  (testing "no key configured → pass"
    (is (nil? (server/check-api-key ""))))
  (testing "configured key mismatch → 401"
    (binding [server/*api-key* "secret"]
      (is (= 401 (:status (server/dispatch-run {:assistant_id "health"}
                                               {:x-api-key "wrong"})))))))

(deftest handle-request-routing
  (is (= 200 (:status (server/handle-request {:method :get :path "/ok"}))))
  (is (= 404 (:status (server/handle-request {:method :get :path "/nope"}))))
  (is (= 200 (:status (server/handle-request {:method :post :path "/xrpc/com.etzhayyim.apps.jukyu.health" :body {}}))))
  (is (= 404 (:status (server/handle-request {:method :post :path "/xrpc/bogus" :body {}})))))

;; ── camelCase → snake_case (mirrors test_camel_to_snake) ─────────────────────

(deftest camel-to-snake-cases
  (is (= "country_code" (server/camel->snake "countryCode")))
  (is (= "risk_score" (server/camel->snake "riskScore")))
  (is (= "product_family" (server/camel->snake "productFamily")))
  (is (= "with_l_l_m" (server/camel->snake "withLLM")))
  (is (= "node_code" (server/camel->snake "nodeCode")))
  (is (= "target_company_did" (server/camel->snake "targetCompanyDid"))))

(deftest snake-input-coercion
  (is (= {:country_code "JP" :risk_score 0.5}
         (server/snake-input {:countryCode "JP" :riskScore 0.5}))))

;; ── health graph end-to-end ─────────────────────────────────────────────────

(deftest health-graph-default-store-down
  (let [out (g/invoke health/GRAPH {})]
    (is (false? (:ok out)) "default store not configured → ok false")
    (is (string? (:server_now out)))))

(deftest health-graph-store-up
  (binding [store/*ping* (fn [] {:rw_ok true :rw_latency_ms 3})]
    (let [out (g/invoke health/GRAPH {})]
      (is (true? (:ok out)))
      (is (= 3 (:rw_latency_ms out))))))

;; ── query_balance / query_supply_chain / rank ───────────────────────────────

(deftest query-balance-not-configured
  (let [out (g/invoke qb/GRAPH {})]
    (is (= [] (:rows out)))
    (is (= store/not-configured (:error out)))))

(deftest query-balance-clamps-and-maps
  (binding [store/*query-balance*
            (fn [filters]
              (is (= 500 (:limit filters)) "limit clamped to 500")
              {:rows [{:domain "naphtha" :countryCode "JP" :productFamily "naphtha"
                       :supplyQuantity 100 :demandQuantity 150 :inventoryQuantity 10
                       :balanceQuantity -50 :confidence 0.7 :latestObservedAt "2026"
                       :observationCount 3}]})]
    (let [out (g/invoke qb/GRAPH {:limit 9999})]
      (is (= 1 (:total out)))
      (is (= "JP" (-> out :rows first :countryCode)))
      (is (= -50.0 (-> out :rows first :balanceQuantity))))))

(deftest query-supply-chain-extracts-unique-nodes
  (binding [store/*query-chain*
            (fn [_filters]
              {:rows [{:edge_id "e1" :domain "naphtha" :relationship "supplies"
                       :src_vid "v1" :src_node_code "A" :src_node_kind "plant" :src_name "Plant A"
                       :src_country_code "JP" :src_operator_did "did:a"
                       :dst_vid "v2" :dst_node_code "B" :dst_node_kind "port" :dst_name "Port B"
                       :dst_country_code "KR" :dst_operator_did "did:b"
                       :capacity_quantity 5 :dependency_weight 0.8 :confidence 0.9}
                      {:edge_id "e2" :domain "naphtha" :relationship "supplies"
                       :src_vid "v1" :src_node_code "A" :src_node_kind "plant" :src_name "Plant A"
                       :src_country_code "JP" :src_operator_did "did:a"
                       :dst_vid "v3" :dst_node_code "C" :dst_node_kind "depot" :dst_name "Depot C"
                       :dst_country_code "CN" :dst_operator_did "did:c"
                       :capacity_quantity 3 :dependency_weight 0.5 :confidence 0.6}]})]
    (let [out (g/invoke qsc/GRAPH {})]
      (is (= 3 (:total_nodes out)) "v1 deduped across two edges")
      (is (= 2 (:total_edges out)))
      (is (= #{"v1" "v2" "v3"} (set (map :nodeId (:nodes out))))))))

(deftest rank-company-exposure-maps
  (binding [store/*query-exposure*
            (fn [filters]
              (is (= 250 (:limit filters)))
              {:rows [{:companyDid "did:co" :companyName "Co" :domain "metals" :countryCode "JP"
                       :riskScore 0.7 :supplyPressure 0.6 :demandPressure 0.2 :pricePressure 0.1
                       :downstreamPressure 0.3 :structuralPressure 0.1 :confidence 0.5
                       :recommendedAction "review" :status "active"}]})]
    (let [out (g/invoke rce/GRAPH {:limit 9999})]
      (is (= 1 (:total out)))
      (is (= 0.7 (-> out :companies first :riskScore))))))

;; ── explain_node guards + stub ──────────────────────────────────────────────

(deftest explain-node-requires-code
  (is (= "node_code is required" (:error (g/invoke en/GRAPH {:node_code ""})))))

(deftest explain-node-not-found
  (binding [store/*explain-fetch* (fn [_] nil)]
    (is (re-find #"node not found" (:error (g/invoke en/GRAPH {:node_code "X"}))))))

(deftest explain-node-happy
  (binding [store/*explain-fetch*
            (fn [code] {:node {:nodeCode code :domain "naphtha"}
                        :chain [{:edgeId "e1"}] :balance [{:domain "naphtha"}]
                        :company_exposure {:companyDid "did:co"}})]
    (let [out (g/invoke en/GRAPH {:node_code "N1"})]
      (is (= "N1" (-> out :node :nodeCode)))
      (is (= 1 (count (:chain out)))))))

;; ── upsert_signal ───────────────────────────────────────────────────────────

(deftest upsert-signal-requires-company
  (let [out (g/invoke us/GRAPH {})]
    (is (false? (:ok out)))
    (is (= "target_company_did is required" (:error out)))))

(deftest upsert-signal-happy-and-severity
  (binding [store/*write-signal* (fn [rec]
                                   (is (= "critical" (:severity rec)) "risk 0.9 → critical")
                                   {:ok true})]
    (let [out (g/invoke us/GRAPH {:target_company_did "did:co" :risk_score 0.9})]
      (is (true? (:ok out)))
      (is (string? (:signal_id out))))))

;; ── extract_shocks: JSON-array parse + LLM stub + Murakumo guard ─────────────

(deftest extract-shocks-requires-text
  (let [out (g/invoke es/GRAPH {:text ""})]
    (is (= "text is required" (:error out)))))

(deftest extract-shocks-parses-and-cleans
  (binding [llm/*chat* (fn [_opts]
                         (str "Here you go: [{\"shock_type\":\"port_closure\",\"domain\":\"naphtha\","
                              "\"country_code\":\"jp\",\"severity\":1.7,\"duration_days\":-3,"
                              "\"description\":\"closed\"}] done"))]
    (let [out (g/invoke es/GRAPH {:text "Some news"})]
      (is (= 1 (:shock_count out)))
      (let [s (first (:shocks out))]
        (is (= "port_closure" (:shockType s)))
        (is (= "JP" (:countryCode s)) "country_code upper-cased + 2-char")
        (is (= 1.0 (:severity s)) "severity clamped to 1.0")
        (is (= 0 (:durationDays s)) "negative duration → 0")))))

(deftest extract-shocks-llm-error
  (binding [llm/*chat* (fn [_opts] {:error "boom"})]
    (let [out (g/invoke es/GRAPH {:text "x"})]
      (is (= "boom" (:error out)))
      (is (= [] (:shocks out))))))

(deftest parse-json-array-tolerates-noise
  (is (= [] (es/parse-json-array "no array here")))
  (is (= [{:a 1}] (es/parse-json-array "prefix [{\"a\":1}] suffix"))))

;; ── export_brief ────────────────────────────────────────────────────────────

(deftest export-brief-empty-outbox
  (let [out (g/invoke eb/GRAPH {})]
    (is (= "No pending signals in outbox." (:brief out)))))

(deftest export-brief-generates
  (binding [store/*read-outbox* (fn [_]
                                  {:rows [{:signalId "s1" :companyDid "did:co" :riskScore 0.7
                                           :confidence 0.6 :severity "high" :domain "naphtha"
                                           :recommendedAction "review" :title "t"}]})
            llm/*chat* (fn [_opts] "Executive brief: situation, companies, actions.")]
    (let [out (g/invoke eb/GRAPH {})]
      (is (= 1 (:signal_count out)))
      (is (re-find #"Executive brief" (:brief out))))))

;; ── notify_company ──────────────────────────────────────────────────────────

(deftest notify-company-requires-signal-id
  (let [out (g/invoke nc/GRAPH {})]
    (is (false? (:ok out)))
    (is (= "signal_id is required" (:error out)))))

(deftest notify-company-dispatch
  (let [updated (atom nil)]
    (binding [store/*load-signal* (fn [sid] {:row {:signal_id sid :target_company_did "did:co"
                                                   :risk_score 0.7 :severity "high"}})
              store/*dispatch-signal* (fn [_payload] {:ok true})
              store/*update-status* (fn [_sid status] (reset! updated status))]
      (let [out (g/invoke nc/GRAPH {:signal_id "sig1"})]
        (is (true? (:ok out)))
        (is (= "dispatched" (:delivery_status out)))
        (is (= "dispatched" @updated))))))

;; ── normalize_domain_adapter ────────────────────────────────────────────────

(deftest normalize-requires-domain
  (is (= "domain is required" (:error (g/invoke nda/GRAPH {:domain ""})))))

(deftest normalize-unsupported-domain
  (is (re-find #"unsupported domain" (:error (g/invoke nda/GRAPH {:domain "widgets"})))))

(deftest normalize-happy
  (binding [store/*normalize-domain* (fn [domain confidence]
                                       (is (= "naphtha" domain))
                                       (is (= 0.72 confidence))
                                       {:upserted_nodes 5 :upserted_edges 2 :upserted_balances 3})]
    (let [out (g/invoke nda/GRAPH {:domain "naphtha"})]
      (is (= 5 (:upserted_nodes out)))
      (is (string? (:freshness_at out))))))

;; ── Pregel verifiable core ──────────────────────────────────────────────────

(deftest compute-risk-weighting
  (is (= 0.30 (pregel/compute-risk {:supply 1.0})))
  (is (= 0.25 (pregel/compute-risk {:supply 0.5 :demand 0.5})))
  (is (= 0.0 (pregel/compute-risk {}))))

(def sample-nodes
  [{:nodeId "n1" :domain "naphtha" :countryCode "JP" :operatorDid "did:co:a"
    :supplyCapacity 100 :demandCapacity 150 :confidence 0.5}
   {:nodeId "n2" :domain "naphtha" :countryCode "JP" :operatorDid "did:co:b"
    :supplyCapacity 100 :demandCapacity 100 :confidence 0.5}])

(def sample-edges
  [{:src "n1" :dst "n2" :dependencyWeight 0.8 :confidence 0.9}])

(def sample-balance
  [{:domain "naphtha" :countryCode "JP" :supplyQuantity 100 :demandQuantity 150
    :balanceQuantity -50 :confidence 0.7}])

(deftest propagate-full-deterministic
  (let [out (pregel/propagate-full {:supply_nodes sample-nodes :supply_edges sample-edges
                                    :balance_rows sample-balance :shock_seeds {} :max_iterations 8})
        exposures (:company_exposures out)]
    (is (seq exposures) "company exposures emitted from operatorDid")
    (is (= 2 (count exposures)))
    (is (apply >= (map :riskScore exposures)) "exposures sorted by riskScore desc")
    (is (boolean? (:converged out)))
    (is (<= (:superstep out) 8) "halts within max_iterations")
    (testing "n1 imbalance seeds supply pressure 0.5"
      (is (>= (get-in out [:node_scores "n1" :supply]) 0.5)))))

(deftest propagate-full-is-deterministic-across-runs
  (let [run #(pregel/propagate-full {:supply_nodes sample-nodes :supply_edges sample-edges
                                     :balance_rows sample-balance :shock_seeds {} :max_iterations 8})]
    (is (= (:company_exposures (run)) (:company_exposures (run))))))

(deftest propagate-equil-variant
  (let [out (pregel/propagate-equil {:supply_nodes sample-nodes :supply_edges sample-edges
                                     :balance_rows sample-balance :max_iterations 8})]
    (is (= 2 (count (:company_exposures out))))
    (is (every? #(contains? % :supplyPressure) (:company_exposures out)))
    (is (not-any? #(contains? % :structuralPressure) (:company_exposures out))
        "equil variant omits structural/price pressures")))

(deftest propagate-empty-no-crash
  (is (= [] (:company_exposures (pregel/propagate-full {})))))

;; ── run_stress_propagation end-to-end (stubbed I/O) ─────────────────────────

(deftest run-stress-propagation-e2e
  (let [written (atom nil)]
    (binding [store/*read-balance-rows* (fn [_] {:rows sample-balance})
              store/*read-chain-rows*   (fn [_] {:nodes sample-nodes :edges sample-edges})
              store/*write-signals-batch* (fn [_run _dom exposures]
                                            (reset! written (count exposures))
                                            {:written 2})
              store/*read-run-outbox*   (fn [_] {:rows [{:signalId "s1"}]})]
      (let [out (g/invoke rsp/GRAPH {:domain "naphtha"})]
        (is (string? (:run_id out)))
        (is (= 2 (:signals_written out)))
        (is (seq (:company_exposures out)))
        (is (= 1 (count (:outbox out))))
        (is (= 0 (:signals_enriched out)) "with_llm unset → no enrichment")))))

(deftest enrichment-cap-is-explicitly-bound
  (binding [rsp/*enrich-max* 1
            llm/*chat* (fn [_] "{}")]
    (is (= 1 (:signals_enriched
              (rsp/node-enrich-signals
               {:with_llm true :domain "energy"
                :company_exposures [{:companyDid "a" :riskScore 0.9}
                                    {:companyDid "b" :riskScore 0.8}]}))))))

;; ── equilibrium end-to-end (stubbed I/O) ─────────────────────────────────────

(deftest equilibrium-e2e
  (binding [store/*read-balance-rows* (fn [_] {:rows sample-balance})
            store/*read-chain-rows*   (fn [_] {:nodes sample-nodes :edges sample-edges})
            store/*write-signals-batch* (fn [_ _ _] {:written 1})
            store/*outbox-pending-count* (fn [] 4)]
    (let [out (g/invoke equil/GRAPH {})]
      (is (re-find #"^jukyu.equil." (:run_id out)))
      (is (= 1 (:signals_written out)))
      (is (= 4 (:outbox_count out)))
      (is (boolean? (:converged out))))))

;; ── cron specs (mirror langgraph.json crons) ─────────────────────────────────

(deftest cron-specs-shape
  (is (= 8 (count cron/cron-specs)))
  (let [equil (first (filter #(= "equilibrium" (:graph %)) cron/cron-specs))]
    (is (= "*/15 * * * *" (:schedule equil)))
    (is (= false (get-in equil [:input :with_llm]))))
  (let [adapter-domains (set (keep (fn [c] (when (= "normalize_domain_adapter" (:graph c))
                                             (get-in c [:input :domain])))
                                   cron/cron-specs))]
    (is (= #{"naphtha" "crude_oil" "energy" "food" "metals" "logistics" "transport"}
           adapter-domains))))

(deftest cron-specs-reference-known-graphs
  (doseq [{:keys [graph]} cron/cron-specs]
    (is (contains? server/GRAPHS graph) (str "cron graph " graph " not in GRAPHS"))))

(deftest cron-policy-is-explicitly-bound
  (is (true? (cron/cron-enabled?)))
  (binding [cron/*enabled?* false]
    (is (false? (cron/cron-enabled?)))))

;; ── Murakumo guard ──────────────────────────────────────────────────────────

(deftest murakumo-guard
  (testing "off-fleet endpoint refused"
    (is (thrown? clojure.lang.ExceptionInfo (llm/assert-murakumo "https://api.openai.com/v1"))))
  (testing "loopback gateway allowed"
    (is (nil? (llm/assert-murakumo "http://127.0.0.1:4000/v1")))))

(deftest outward-capabilities-fail-closed
  (is (thrown-with-msg? clojure.lang.ExceptionInfo #"explicit chat capability"
                        (llm/chat {:user "x"})))
  (is (thrown-with-msg? clojure.lang.ExceptionInfo #"explicit run-server capability"
                        (server/serve 2027)))
  (is (thrown? clojure.lang.ExceptionInfo (llm/assert-murakumo "not-a-url"))))

(deftest injected-murakumo-wire-contract
  (let [seen (atom nil)
        out (llm/chat-with
             (fn [url opts]
               (reset! seen {:url url :opts opts})
               {:status 200 :body "{\"choices\":[{\"message\":{\"content\":\" ok \"}}]}"})
             {:url "http://127.0.0.1:4000" :timeout-sec 2 :api-key "k"}
             {:model "m" :user "u" :max-tokens 9})]
    (is (= "ok" out))
    (is (= "http://127.0.0.1:4000/v1/chat/completions" (:url @seen)))
    (is (= "Bearer k" (get-in @seen [:opts :headers "Authorization"])))
    (is (= 2000 (get-in @seen [:opts :timeout])))))

(deftest injected-server-capability
  (let [seen (atom nil) stop (fn [] :stopped)]
    (is (identical? stop (server/serve (fn [handler opts]
                                         (reset! seen [handler opts]) stop) 0)))
    (is (fn? (first @seen)))
    (is (= {:port 0} (second @seen)))))

;; ── util sanity ─────────────────────────────────────────────────────────────

(deftest severity-ladder
  (is (= "critical" (util/severity 0.85)))
  (is (= "high" (util/severity 0.65)))
  (is (= "medium" (util/severity 0.45)))
  (is (= "low" (util/severity 0.1)))
  (is (= "medium" (util/severity3 0.45)) "equil 3-bucket folds low→medium"))
