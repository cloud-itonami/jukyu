(ns lg-jukyu.graphs.extract-shocks
  "jukyu `extractShocks` graph — news text → structured shock events.

  NSID: com.etzhayyim.apps.jukyu.extractShocks   Model: qwen3-30b
  Faithful clj port of `extract_shocks.py`. Topology: START → extract → audit → END.
  Calls the LLM (Murakumo loopback default), greedily parses a JSON array out of
  the response, then validates/clamps each shock. DEVIATION: httpx→`llm/*chat*`."
  (:require #?(:clj [cheshire.core :as json])
            [langgraph.graph :as g]
            [clojure.string :as str]
            [lg-jukyu.llm :as llm]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.util :as util]))

(def system-prompt
  (str "You are a commodity supply-chain analyst.\n"
       "Extract supply-demand shock events from the provided news text.\n"
       "Return a valid JSON array. Each item must have these fields:\n"
       "  shock_type: string (one of: cargo_delay, port_closure, plant_outage, war_risk,\n"
       "               price_spike, demand_surge, inventory_drawdown, sanctions, weather, other)\n"
       "  domain: string (one of: naphtha, crude_oil, semiconductor, energy, food, metals, logistics, transport, unknown)\n"
       "  country_code: string (ISO-3166-1 alpha-2 or XX if unknown)\n"
       "  severity: float (0.0 to 1.0)\n"
       "  duration_days: integer (estimated disruption days; 0 if unknown)\n"
       "  description: string (one sentence summary)\n"
       "  source_url: string or null\n\n"
       "Output ONLY the JSON array, no other text."))

(defn parse-json-array
  "Greedy [...] extraction + parse (mirrors python re.search(r\"\\[.*\\]\", DOTALL))."
  [content]
  (try
    (let [s (str content)
        i (str/index-of s "[")
          j (str/last-index-of s "]")]
      (if (and i j (< i j))
        (json/parse-string (subs s i (inc j)) true)
        []))
    (catch Exception _ [])))

(defn- clean-shock [s]
  (when (map? s)
    {:shockType (str (get s :shock_type "other"))
     :domain (str (get s :domain "unknown"))
     :countryCode (-> (str (get s :country_code "XX")) (subs 0 (min 2 (count (str (get s :country_code "XX"))))) str/upper-case)
     :severity (min 1.0 (max 0.0 (util/as-float (get s :severity 0.5) 0.5)))
     :durationDays (max 0 (util/as-int (get s :duration_days 0) 0))
     :description (util/clip (str (get s :description "")) 300)
     :sourceUrl (or (get s :source_url) nil)}))

(defn node-extract [state]
  (let [text (str/trim (or (:text state) ""))]
    (if (str/blank? text)
      {:shocks [] :shock_count 0 :error "text is required"}
      (let [res (llm/chat {:model llm/extraction-model
                             :system system-prompt
                             :user (str "News text:\n\n" (util/clip text 4000))
                             :max-tokens 2048 :temperature 0.1})]
        (if (map? res) ;; {:error ...}
          {:shocks [] :shock_count 0 :error (:error res)}
          (let [src-url (:source_url state)
                cleaned (->> (parse-json-array res)
                             (keep clean-shock)
                             (mapv (fn [s] (update s :sourceUrl #(or % src-url)))))]
            {:shocks cleaned :shock_count (count cleaned)}))))))

(defn node-audit [state]
  (audit/emit-audit {:activity "jukyu.extractShocks"
                     :object-id (str "shocks:" (quot (System/currentTimeMillis) 1000))
                     :object-type "jukyu.shockEvent"
                     :attributes {:shockCount (:shock_count state 0)}})
  {})

(defn build []
  (-> (g/state-graph)
      (g/add-node :extract node-extract)
      (g/add-node :audit node-audit)
      (g/add-edge :extract :audit)
      (g/set-entry-point :extract)
      (g/set-finish-point :audit)
      (g/compile-graph)))

(def GRAPH (build))
