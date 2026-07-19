(ns lg-jukyu.host
  "Existing host-only entrypoint for tests and explicit live capabilities."
  (:require [babashka.http-client :as http]
            [cheshire.core :as json]
            [clojure.string :as str]
            [clojure.test :as t]
            [org.httpkit.server :as httpkit]
            [lg-jukyu.audit :as audit]
            [lg-jukyu.cron :as cron]
            [lg-jukyu.graphs.run-stress-propagation :as stress]
            [lg-jukyu.llm :as llm]
            [lg-jukyu.server :as server]
            [lg-jukyu.smoke-test]))

(defn- env [name default] (or (System/getenv name) default))

(def murakumo-config
  {:url (env "JUKYU_LLM_URL" (:url llm/default-config))
   :timeout-sec (Double/parseDouble (env "JUKYU_LLM_TIMEOUT" "30"))
   :api-key (env "JUKYU_LLM_API_KEY" "")})

(def audit-config
  {:url (env "BPMN_DISPATCHER_INTERNAL_URL"
             "http://bpmn-dispatcher.mitama-udf.svc.cluster.local:8080")
   :secret (env "BPMN_DISPATCHER_INTERNAL_SECRET" "")
   :timeout-sec (Double/parseDouble (env "LG_AUDIT_TIMEOUT_SEC" "3.0"))
   :disabled? (= "1" (env "LG_AUDIT_DISABLED" "0"))
   :app-did (env "JUKYU_APP_DID" "did:web:jukyu.etzhayyim.com")})

(def api-key (env "LG_API_KEY" ""))
(def cron-enabled?
  (contains? #{"1" "true" "yes"}
             (str/lower-case (env "LG_CRON_ENABLED" "true"))))
(def enrich-max (Long/parseLong (env "JUKYU_LLM_ENRICH_MAX" "10")))

(defn murakumo-chat [opts]
  (llm/chat-with http/post murakumo-config opts))

(defn audit-sink [event]
  (try
    (http/post (str (str/replace (:url audit-config) #"/+$" "")
                    "/xrpc/com.etzhayyim.generic.audit.emit")
               {:headers (cond-> {"Content-Type" "application/json"}
                           (seq (:secret audit-config))
                           (assoc "x-internal-trust" (:secret audit-config)))
                :timeout (long (* 1000 (:timeout-sec audit-config)))
                :body (json/generate-string event)})
    nil
    (catch Exception _ nil)))

(defn handler [request]
  (binding [llm/*chat* murakumo-chat
            audit/*audit-sink* audit-sink
            audit/*disabled?* (:disabled? audit-config)
            audit/*app-did* (:app-did audit-config)
            cron/*enabled?* cron-enabled?
            stress/*enrich-max* enrich-max
            server/*api-key* api-key]
    (server/ring-handler request)))

(defn start-server! [port]
  (server/serve (fn [_portable-handler options]
                  (httpkit/run-server handler options))
                port))

(defn run-tests! []
  (let [{:keys [fail error]} (t/run-tests 'lg-jukyu.smoke-test)]
    (when (pos? (+ (or fail 0) (or error 0))) (System/exit 1))))

(if (= "--server" (first *command-line-args*))
  (let [port (if-let [value (second *command-line-args*)]
               (Long/parseLong value) 2027)]
    (start-server! port)
    @(promise))
  (run-tests!))
