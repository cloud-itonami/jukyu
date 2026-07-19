(ns lg-jukyu.pregel
  "Bounded Pregel stress-propagation core — the VERIFIABLE compute heart of jukyu,
  ported faithfully from `propagate` in `run_stress_propagation.py` and
  `equilibrium.py`. No I/O: pure functions over plain maps, so the risk-score
  weighting, the confidence formula, and the halting rule are deterministically
  testable under bb.

  Risk score : 0.30·supply + 0.20·demand + 0.20·price + 0.20·downstream + 0.10·structural
  Confidence : freshness(30%) + reliability(25%) + connectivity(20%) + cargo/price(15%) + corroboration(10%)
  Halting    : ≤ max_iterations supersteps; stop after 2 consecutive supersteps with max-delta < 0.03."
  (:require [lg-jukyu.util :as util]))

(def risk-weights
  {:supply 0.30 :demand 0.20 :price 0.20 :downstream 0.20 :structural 0.10})

;; Domain reliability priors (confidence formula reliability component, weight 0.25).
(def domain-reliability
  {"naphtha" 0.72 "crude_oil" 0.60 "semiconductor" 0.60
   "energy" 0.45 "food" 0.40 "metals" 0.40
   "logistics" 0.42 "transport" 0.56})

(defn compute-risk
  "Weighted risk = Σ score·weight (mirrors python `_compute_risk`)."
  [scores]
  (+ (* (double (get scores :supply 0)) 0.30)
     (* (double (get scores :demand 0)) 0.20)
     (* (double (get scores :price 0)) 0.20)
     (* (double (get scores :downstream 0)) 0.20)
     (* (double (get scores :structural 0)) 0.10)))

(defn- upstream-index
  "dst-nodeId -> [edges] (mirrors the `upstream` adjacency map)."
  [edges]
  (reduce (fn [m e] (update m (:dst e) (fnil conj []) e)) {} edges))

(defn- balance-index
  "(domain.country) -> balance row."
  [rows]
  (reduce (fn [m b] (assoc m (str (:domain b) "." (:countryCode b)) b)) {} rows))

(defn- edge-count
  "nodeId -> incident edge count (connectivity component)."
  [edges]
  (reduce (fn [m e]
            (cond-> m
              (seq (str (:src e))) (update (:src e) (fnil inc 0))
              (seq (str (:dst e))) (update (:dst e) (fnil inc 0))))
          {} edges))

(defn init-scores-full
  "Initial node scores for run_stress_propagation (full confidence formula +
  shock-seed seeding)."
  [supply-nodes balance-idx shock-seeds edge-cnt]
  (reduce
   (fn [m n]
     (let [nid     (:nodeId n)
           dom     (:domain n)
           cc      (:countryCode n)
           bal-key (str dom "." cc)
           bal     (get balance-idx bal-key {})
           seed    (util/as-float (get shock-seeds bal-key 0.0) 0.0)
           supply-t (util/as-float (or (:supplyCapacity n) 1) 1.0)
           demand-t (util/as-float (or (:demandCapacity n) supply-t) supply-t)
           imbalance (if (> supply-t 0)
                       (max 0.0 (/ (- demand-t supply-t) (max supply-t 1.0)))
                       0.0)
           freshness   (if (seq bal) 0.70 0.30)
           reliability (get domain-reliability dom 0.40)
           n-edges     (get edge-cnt nid 0)
           connectivity (min 1.0 (Math/sqrt (/ (double n-edges) 10.0)))
           cargo-price (if (or (> (util/as-float (:supplyQuantity bal) 0) 0)
                               (not= (util/as-float (:balanceQuantity bal) 0) 0.0))
                         1.0 0.0)
           corroboration (util/as-float (:confidence bal) 0.5)
           confidence  (util/round4 (+ (* 0.30 freshness)
                                       (* 0.25 reliability)
                                       (* 0.20 connectivity)
                                       (* 0.15 cargo-price)
                                       (* 0.10 corroboration)))]
       (assoc m nid
              {:supply (min 1.0 (max imbalance seed))
               :demand (if (seq bal)
                         (/ (util/as-float (:demandQuantity bal) 0)
                            (max (util/as-float (:supplyQuantity bal) 1) 1.0))
                         0.0)
               :price 0.0 :downstream 0.0 :structural 0.0
               :confidence confidence})))
   {} supply-nodes))

(defn init-scores-equil
  "Initial node scores for the equilibrium loop (uses node confidence directly,
  no shock seeds / reliability formula)."
  [supply-nodes balance-idx]
  (reduce
   (fn [m n]
     (let [nid (:nodeId n)
           bal (get balance-idx (str (:domain n) "." (:countryCode n)) {})
           supply-t (util/as-float (or (:supplyCapacity n) 1) 1.0)
           demand-t (util/as-float (or (:demandCapacity n) supply-t) supply-t)
           imbalance (max 0.0 (/ (- demand-t supply-t) (max supply-t 1.0)))]
       (assoc m nid
              {:supply (min 1.0 imbalance)
               :demand (if (seq bal)
                         (/ (util/as-float (:demandQuantity bal) 0)
                            (max (util/as-float (:supplyQuantity bal) 1) 1.0))
                         0.0)
               :price 0.0 :downstream 0.0 :structural 0.0
               :confidence (util/as-float (:confidence n) 0.5)})))
   {} supply-nodes))

(defn run-supersteps
  "Iterate bounded supersteps. Returns {:scores :superstep :converged}.
  Faithful to both python loops: aggregate upstream pressure, fold into
  supply/downstream, halt after 2 consecutive deltas < 0.03."
  [node-scores upstream-idx max-iter]
  (loop [step 0
         scores node-scores
         stable 0]
    (if (>= step max-iter)
      {:scores scores :superstep step :converged (>= stable 2)}
      (let [[new-scores max-delta]
            (reduce
             (fn [[acc md] [nid sc]]
               (let [up-edges (get upstream-idx nid [])
                     raw (reduce (fn [p e]
                                   (let [src (:src e)]
                                     (if (contains? scores src)
                                       (+ p (* (compute-risk (get scores src))
                                               (util/as-float (:dependencyWeight e) 0.5)
                                               (util/as-float (:confidence e) 0.5)))
                                       p)))
                                 0.0 up-edges)
                     up-pressure (if (seq up-edges) (min 1.0 (/ raw (count up-edges))) raw)
                     new (assoc sc
                                :supply (min 1.0 (+ (get sc :supply 0) (* up-pressure 0.5)))
                                :downstream (min 1.0 up-pressure))
                     delta (Math/abs (- (compute-risk new) (compute-risk sc)))]
                 [(assoc acc nid new) (max md delta)]))
             [{} 0.0] scores)
            stable' (if (< max-delta 0.03) (inc stable) 0)]
        (if (>= stable' 2)
          {:scores new-scores :superstep (inc step) :converged true}
          (recur (inc step) new-scores stable'))))))

(defn aggregate-companies-full
  "Aggregate node scores → company exposures (run_stress_propagation variant:
  all five pressure dimensions)."
  [scores supply-nodes]
  (let [node-by-id (into {} (map (juxt :nodeId identity)) supply-nodes)
        company-map (reduce (fn [m [nid sc]]
                              (let [op (get-in node-by-id [nid :operatorDid] "")]
                                (if (seq op)
                                  (update m op (fnil conj [])
                                          (assoc sc :risk (compute-risk sc)))
                                  m)))
                            {} scores)]
    (->> company-map
         (map (fn [[op node-list]]
                (let [n (count node-list)
                      avg (fn [k] (util/round4 (/ (reduce + (map #(get % k 0) node-list)) n)))]
                  {:companyDid op
                   :riskScore (util/round4 (/ (reduce + (map :risk node-list)) n))
                   :supplyPressure (avg :supply)
                   :demandPressure (avg :demand)
                   :pricePressure (avg :price)
                   :downstreamPressure (avg :downstream)
                   :structuralPressure (avg :structural)
                   :confidence (util/round4 (/ (reduce + (map #(get % :confidence 0.5) node-list)) n))
                   :nodeCount n})))
         (sort-by :riskScore >)
         vec)))

(defn aggregate-companies-equil
  "Aggregate node scores → company exposures (equilibrium variant: supply +
  demand pressures only)."
  [scores supply-nodes]
  (let [node-by-id (into {} (map (juxt :nodeId identity)) supply-nodes)
        company-map (reduce (fn [m [nid sc]]
                              (let [op (get-in node-by-id [nid :operatorDid] "")]
                                (if (seq op)
                                  (update m op (fnil conj [])
                                          (assoc sc :risk (compute-risk sc)))
                                  m)))
                            {} scores)]
    (->> company-map
         (map (fn [[op node-list]]
                (let [n (count node-list)
                      avg (fn [k] (util/round4 (/ (reduce + (map #(get % k 0) node-list)) n)))]
                  {:companyDid op
                   :riskScore (util/round4 (/ (reduce + (map :risk node-list)) n))
                   :supplyPressure (avg :supply)
                   :demandPressure (avg :demand)
                   :confidence (util/round4 (/ (reduce + (map #(get % :confidence 0.5) node-list)) n))
                   :nodeCount n})))
         (sort-by :riskScore >)
         vec)))

(defn propagate-full
  "Full run_stress_propagation propagate node (pure). Returns the state delta:
  {:node_scores :company_exposures :superstep :converged}."
  [{:keys [supply_nodes supply_edges balance_rows shock_seeds max_iterations]}]
  (let [supply-nodes (or supply_nodes [])
        edges        (or supply_edges [])
        up-idx       (upstream-index edges)
        bal-idx      (balance-index (or balance_rows []))
        edge-cnt     (edge-count edges)
        init         (init-scores-full supply-nodes bal-idx (or shock_seeds {}) edge-cnt)
        {:keys [scores superstep converged]} (run-supersteps init up-idx (or max_iterations 8))]
    {:node_scores scores
     :company_exposures (aggregate-companies-full scores supply-nodes)
     :superstep superstep
     :converged converged}))

(defn propagate-equil
  "Equilibrium propagate node (pure)."
  [{:keys [supply_nodes supply_edges balance_rows max_iterations]}]
  (let [supply-nodes (or supply_nodes [])
        edges        (or supply_edges [])
        up-idx       (upstream-index edges)
        bal-idx      (balance-index (or balance_rows []))
        init         (init-scores-equil supply-nodes bal-idx)
        {:keys [scores superstep converged]} (run-supersteps init up-idx (or max_iterations 8))]
    {:node_scores scores
     :company_exposures (aggregate-companies-equil scores supply-nodes)
     :superstep superstep
     :converged converged}))
