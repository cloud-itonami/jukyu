(ns lg-jukyu.graphs.rank-company-exposure
  "jukyu `rankCompanyExposure` graph — read mv_jukyu_company_exposure_rank.

  NSID: com.etzhayyim.apps.jukyu.rankCompanyExposure
  Faithful clj port of `rank_company_exposure.py`. Topology: START → query →
  audit → END. Filters: domain, country_code, min_risk_score; limit clamped to
  [1,250]. DEVIATION: psycopg → `store/*query-exposure*` seam."
  (:require [langgraph.graph :as g]
            [lg-jukyu.store :as store]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]))

(defn node-query [state]
  (let [limit (util/clamp (util/as-int (:limit state) 50) 1 250)
        res   (store/*query-exposure* {:domain (:domain state)
                                       :country_code (:country_code state)
                                       :min_risk_score (util/as-float (:min_risk_score state) 0.0)
                                       :limit limit})]
    (if (:error res)
      {:error (:error res) :companies []}
      (let [companies (mapv (fn [r]
                              {:companyDid (:companyDid r)
                               :companyName (or (:companyName r) "")
                               :domain (:domain r)
                               :countryCode (or (:countryCode r) "")
                               :riskScore (util/as-float (:riskScore r) 0)
                               :supplyPressure (util/as-float (:supplyPressure r) 0)
                               :demandPressure (util/as-float (:demandPressure r) 0)
                               :pricePressure (util/as-float (:pricePressure r) 0)
                               :downstreamPressure (util/as-float (:downstreamPressure r) 0)
                               :structuralPressure (util/as-float (:structuralPressure r) 0)
                               :confidence (util/as-float (:confidence r) 0)
                               :recommendedAction (or (:recommendedAction r) "")
                               :status (or (:status r) "active")})
                            (:rows res))]
        {:companies companies :total (count companies)}))))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.rankCompanyExposure"
                     :object-id (str "rankCompanyExposure:" (quot (System/currentTimeMillis) 1000))
                     :object-type "jukyu.companyExposure"
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
