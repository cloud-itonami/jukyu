(ns lg-jukyu.server
  "lg-jukyu dispatch surface — clj port of `lg/lg_jukyu/server.py` (ADR-2606280030).

  The Python file is a FastAPI app exposing:
    POST /runs                          → invoke a graph synchronously
    POST /runs/stream                   → SSE stream (out of scope here; deferred)
    POST /xrpc/{nsid}                   → XRPC shim (NSID → assistant_id)
    POST /export/brief                  → exportBrief graph (gemma-4-e4b-it)
    POST /extract/shocks                → extractShocks graph (qwen3-30b)
    POST /cron/domain-adapter/{domain}  → normalize_domain_adapter
    GET  /ok | /health                  → liveness / readiness

  This namespace ports the GRAPHS registry, the NSID→assistant map, the
  camelCase→snake_case body coercion, and the invoke/serialize logic as plain clj
  functions (`dispatch-run`, `dispatch-xrpc`, `export-brief`, `extract-shocks`,
  `trigger-domain-adapter`, `health`) plus a pure ring-ish `handle-request`
  dispatcher. Binding `handle-request` to a concrete socket (org.httpkit.server)
  is the one remaining infra leg — see `serve` below; the deployed FastAPI pod
  (`lg/`) remains the live runtime and COEXISTS."
  (:require #?(:clj [cheshire.core :as json])
            [clojure.string :as str]
            [langgraph.graph :as g]
            [lg-jukyu.graphs.health :as health]
            [lg-jukyu.graphs.query-balance :as query-balance]
            [lg-jukyu.graphs.query-supply-chain :as query-supply-chain]
            [lg-jukyu.graphs.rank-company-exposure :as rank-company-exposure]
            [lg-jukyu.graphs.explain-node :as explain-node]
            [lg-jukyu.graphs.run-stress-propagation :as run-stress-propagation]
            [lg-jukyu.graphs.upsert-signal :as upsert-signal]
            [lg-jukyu.graphs.export-brief :as export-brief]
            [lg-jukyu.graphs.notify-company :as notify-company]
            [lg-jukyu.graphs.normalize-domain-adapter :as normalize-domain-adapter]
            [lg-jukyu.graphs.extract-shocks :as extract-shocks]
            [lg-jukyu.graphs.equilibrium :as equilibrium]))

(def GRAPHS
  {"health"                   health/GRAPH
   "query_balance"            query-balance/GRAPH
   "query_supply_chain"       query-supply-chain/GRAPH
   "rank_company_exposure"    rank-company-exposure/GRAPH
   "explain_node"             explain-node/GRAPH
   "run_stress_propagation"   run-stress-propagation/GRAPH
   "upsert_signal"            upsert-signal/GRAPH
   "export_brief"             export-brief/GRAPH
   "notify_company"           notify-company/GRAPH
   "normalize_domain_adapter" normalize-domain-adapter/GRAPH
   "extract_shocks"           extract-shocks/GRAPH
   "equilibrium"              equilibrium/GRAPH})

(def NSID-MAP
  {"com.etzhayyim.apps.jukyu.health"                 "health"
   "com.etzhayyim.apps.jukyu.queryBalance"           "query_balance"
   "com.etzhayyim.apps.jukyu.querySupplyChain"       "query_supply_chain"
   "com.etzhayyim.apps.jukyu.rankCompanyExposure"    "rank_company_exposure"
   "com.etzhayyim.apps.jukyu.explainNode"            "explain_node"
   "com.etzhayyim.apps.jukyu.runStressPropagation"   "run_stress_propagation"
   "com.etzhayyim.apps.jukyu.upsertSignal"           "upsert_signal"
   "com.etzhayyim.apps.jukyu.exportBrief"            "export_brief"
   "com.etzhayyim.apps.jukyu.notifyCompany"          "notify_company"
   "com.etzhayyim.apps.jukyu.normalizeDomainAdapter" "normalize_domain_adapter"
   "com.etzhayyim.apps.jukyu.extractShocks"          "extract_shocks"})

(def ^:dynamic *api-key* "")

(defn camel->snake
  "Mirror of server._camel_to_snake: prepend `_` before each interior uppercase
  char, then lowercase. e.g. countryCode→country_code, withLLM→with_l_l_m."
  [s]
  (->> (map-indexed (fn [i ch]
                      (if (and #?(:clj (Character/isUpperCase ^char ch)
                                  :cljs (and (not= ch (str/lower-case (str ch))) (= ch (first (str/upper-case (str ch))))))
                               (pos? i))
                        (str "_" (str/lower-case (str ch)))
                        (str/lower-case (str ch))))
                    (str s))
       (apply str)))

(defn snake-input
  "camelCase body map (keyword keys) → snake_case keyword-keyed graph input."
  [body]
  (reduce-kv (fn [m k v] (assoc m (keyword (camel->snake (name k))) v)) {} (or body {})))

(defn check-api-key
  "Mirrors server._require_api_key: if LG_API_KEY is set, x-api-key must match."
  [x-api-key]
  (if (and (seq *api-key*) (not= x-api-key *api-key*))
    {:status 401 :body {:detail "invalid x-api-key"}}
    nil))

(defn- run-graph [graph input]
  (try
    {:status 200 :body (g/invoke graph (or input {}))}
    (catch Exception e
      {:status 500 :body {:error (let [m (str (.getMessage e))]
                                   (subs m 0 (min 300 (count m))))}})))

(defn health
  "GET /ok | /health → {:ok true :graphs [...] :version ...}"
  []
  {:status 200 :body {:ok true :graphs (vec (keys GRAPHS)) :version "0.1.0"}})

(defn dispatch-run
  "POST /runs body → {:status :body}. body keys: :assistant_id :input.
  Enforces the optional x-api-key (pass via opts {:x-api-key ...})."
  ([body] (dispatch-run body {}))
  ([body {:keys [x-api-key]}]
   (or (check-api-key x-api-key)
       (let [aid   (or (:assistant_id body) "")
             graph (get GRAPHS aid)]
         (if (nil? graph)
           {:status 404 :body {:error (str "unknown graph: " aid)}}
           (run-graph graph (or (:input body) {})))))))

(defn dispatch-xrpc
  "POST /xrpc/{nsid} body → {:status :body}. NSID mapped to assistant_id; body
  camelCase keys are coerced to snake_case graph input. /xrpc is unauthenticated
  (parity with the Python server — trust at the cloudflared tunnel layer)."
  [nsid body]
  (let [aid (get NSID-MAP nsid)]
    (if (nil? aid)
      {:status 404 :body {:error (str "unknown NSID: " nsid)}}
      (run-graph (get GRAPHS aid) (snake-input body)))))

(defn export-brief
  "POST /export/brief — exportBrief graph over a camelCase body."
  [body]
  (run-graph (get GRAPHS "export_brief") (snake-input body)))

(defn extract-shocks
  "POST /extract/shocks — extractShocks graph over a camelCase body."
  [body]
  (run-graph (get GRAPHS "extract_shocks") (snake-input body)))

(defn trigger-domain-adapter
  "POST /cron/domain-adapter/{domain} — normalize_domain_adapter, domain from path
  (body may override missing keys; :domain defaults to the path segment)."
  [domain body]
  (let [input (-> (snake-input body) (update :domain #(or % domain)))]
    (run-graph (get GRAPHS "normalize_domain_adapter") input)))

(defn handle-request
  "Pure ring-ish dispatcher. req = {:method :path :headers :query :body}.
  -> {:status :body}. Deterministically testable; bind to a socket via `serve`."
  [{:keys [method path headers body]}]
  (let [method  (keyword (str/lower-case (name method)))
        x-key   (get headers "x-api-key")
        adapter (second (re-matches #"/cron/domain-adapter/(.+)" (str path)))
        nsid    (second (re-matches #"/xrpc/(.+)" (str path)))]
    (cond
      (and (= :get method) (#{"/ok" "/health"} path)) (health)
      (and (= :post method) (= path "/runs"))          (dispatch-run body {:x-api-key x-key})
      (and (= :post method) (= path "/export/brief"))  (export-brief body)
      (and (= :post method) (= path "/extract/shocks")) (extract-shocks body)
      (and (= :post method) adapter)                   (trigger-domain-adapter adapter body)
      (and (= :post method) nsid)                      (dispatch-xrpc nsid body)
      :else {:status 404 :body {:detail "not found"}})))

(defn ring-handler [{:keys [request-method uri headers] :as req}]
  #?(:clj
     (let [body (when-let [b (:body req)]
                  (try (json/parse-string (slurp b) true) (catch Exception _ nil)))
           {:keys [status body]} (handle-request
                                  {:method request-method :path uri
                                   :headers headers :body body})]
       {:status status :headers {"Content-Type" "application/json"}
        :body (json/generate-string body)})
     :default {:status 501 :body {:detail "host server unavailable"}}))

#?(:clj
   (defn serve
     "Optional: bind `handle-request` to org.httpkit.server (bundled in babashka).
     Deployment-deferred — the live FastAPI pod is the deployed runtime; this is
     here only so the clj twin can stand up a socket when a human cuts over.
     JSON encode/decode via cheshire."
     ([port] (serve nil port))
     ([run-server port]
      (when-not (fn? run-server)
        (throw (ex-info "Jukyu server requires an explicit run-server capability"
                        {:capability :jukyu/run-server})))
      (run-server ring-handler {:port port}))))
