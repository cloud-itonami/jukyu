(ns lg-jukyu.graphs.export-brief
  "jukyu `exportBrief` graph — LLM executive brief from latest outbox.

  NSID: com.etzhayyim.apps.jukyu.exportBrief   Model: gemma-4-e4b-it
  Faithful clj port of `export_brief.py`. Topology: START → read_outbox →
  generate_brief → audit → END. DEVIATION: psycopg→`store/*read-outbox*`,
  httpx→`llm/*chat*`."
  (:require [langgraph.graph :as g]
            [clojure.string :as str]
            [lg-jukyu.store :as store]
            [lg-jukyu.llm :as llm]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]))

(defn node-read-outbox [state]
  (let [limit (util/clamp (util/as-int (:limit state) 20) 1 50)
        res   (store/*read-outbox* {:domain (:domain state) :limit limit})]
    (if (:error res)
      {:outbox [] :signal_count 0 :error (:error res)}
      (let [outbox (mapv (fn [r]
                           {:signalId (:signalId r) :companyDid (:companyDid r)
                            :riskScore (util/as-float (:riskScore r) 0)
                            :confidence (util/as-float (:confidence r) 0)
                            :severity (:severity r) :domain (:domain r)
                            :recommendedAction (:recommendedAction r) :title (:title r)})
                         (:rows res))]
        {:outbox outbox :signal_count (count outbox)}))))

(defn- fmt [x] (format "%.2f" (double x)))

(defn node-generate-brief [state]
  (let [outbox (or (:outbox state) [])]
    (if (empty? outbox)
      {:brief "No pending signals in outbox."}
      (let [domain (or (:domain state) "global")
            signals-text (str/join "\n"
                           (map (fn [s]
                                  (str "- [" (str/upper-case (str (:severity s))) "] "
                                       (or (:companyDid s) "?")
                                       " (risk=" (fmt (:riskScore s 0)) ", conf=" (fmt (:confidence s 0)) "): "
                                       (or (:recommendedAction s) "")))
                                (take 20 outbox)))
            prompt (str "Write a 3-paragraph executive brief about the following supply-chain risk signals "
                        "for domain: " domain ".\n\n"
                        "Signals:\n" signals-text "\n\n"
                        "Format: (1) Situation overview (2) Top companies at risk with key facts "
                        "(3) Recommended actions. Be concise and precise.")
            res (llm/chat {:model llm/narrative-model
                             :system "You are a senior commodity risk analyst writing executive briefs."
                             :user prompt :max-tokens 1024 :temperature 0.5})]
        (if (map? res)
          {:brief (util/clip (str "Brief generation failed: " (:error res)) 300)}
          {:brief res})))))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.exportBrief"
                     :object-id (str "brief:" (quot (System/currentTimeMillis) 1000))
                     :object-type "jukyu.brief"
                     :attributes {:signalCount (:signal_count state 0) :domain (:domain state)}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :read_outbox node-read-outbox)
      (g/add-node :generate_brief node-generate-brief)
      (g/add-node :audit node-audit)
      (g/add-edge :read_outbox :generate_brief)
      (g/add-edge :generate_brief :audit)
      (g/set-entry-point :read_outbox)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
