(ns lg-jukyu.llm
  "LLM edge for the jukyu clj port — clj analogue of the httpx LiteLLM calls in
  `extract_shocks.py` / `export_brief.py` / `run_stress_propagation.py`.

  DEVIATION (noted): the Python posts to `JUKYU_LLM_URL` (`llm.etzhayyim.com`
  LiteLLM gateway → murakumo-serve fleet). Per ADR-2605215000 / ADR-2606172359
  (Murakumo DEFAULT-PREFERRED) the default endpoint here is the Murakumo loopback
  gateway (LiteLLM 127.0.0.1:4000) and `assert-murakumo` refuses any off-fleet
  host (ibuki/recap pattern). The model ids (qwen3-30b extraction / gemma-4-e4b-it
  narrative) are preserved.

  `*chat*` is the single injectable edge (tests rebind to stubs)."
  (:require #?(:clj [cheshire.core :as json])
            [clojure.string :as str]
            [lg-jukyu.util :as util]))

;; Murakumo fleet (ADR-2605215000) — the ONLY inference endpoints representable.
(def murakumo-allowed-hosts
  #{"127.0.0.1:4000" "localhost:4000"
    "192.168.1.70:8077" "192.168.1.70:11434"
    "127.0.0.1:11434" "localhost:11434"})

(def default-config {:url "http://127.0.0.1:4000" :timeout-sec 30.0 :api-key ""})
(def extraction-model "qwen3-30b")
(def narrative-model "gemma-4-e4b-it")

(defn assert-murakumo
  "Refuse any LLM endpoint outside the Murakumo fleet (http only)."
  [endpoint]
  (let [[_ scheme host] (or (re-find #"^([A-Za-z][A-Za-z0-9+.\-]*)://([^/?#]*)" (str endpoint))
                            [nil nil nil])]
    (when-not (and (= "http" (some-> scheme str/lower-case))
                   (contains? murakumo-allowed-hosts (some-> host str/lower-case)))
      (throw (ex-info (str "inference endpoint " (pr-str endpoint)
                           " is outside the Murakumo fleet (ADR-2605215000)")
                      {:murakumo-only-violation true :endpoint endpoint})))))

(defn chat-with
  "POST through an explicit HTTP capability to the Murakumo loopback
  gateway. opts = {:model :system :user :messages :max-tokens :temperature}.
  Returns the assistant content string, or {:error ...}."
  [http-post {:keys [url timeout-sec api-key] :or {url (:url default-config)
                                                   timeout-sec (:timeout-sec default-config)
                                                   api-key ""}}
   {:keys [model system user messages max-tokens temperature]}]
  (when-not (fn? http-post)
    (throw (ex-info "Jukyu inference requires an explicit HTTP POST capability"
                    {:capability :jukyu/murakumo-http-post})))
  (let [url (str/replace (str url) #"/+$" "")]
    (assert-murakumo url)
  (try
    (let [msgs     (or messages
                       [{:role "system" :content (or system "")}
                        {:role "user"   :content (or user "")}])
          headers  (cond-> {"Content-Type" "application/json"}
                     (seq api-key) (assoc "Authorization" (str "Bearer " api-key)))
          resp     (http-post (str url "/v1/chat/completions")
                         {:headers headers
                          :timeout (long (* 1000 (double timeout-sec)))
                          :body (json/generate-string {:model (or model narrative-model)
                                           :messages msgs
                                           :max_tokens (or max-tokens 1024)
                                           :temperature (or temperature 0.3)})})
          status   (:status resp)]
      (if (>= status 400)
        {:error (str "llm " status ": " (util/clip (:body resp) 200))}
        (let [body (json/parse-string (:body resp) true)
              txt  (some-> (get-in body [:choices 0 :message :content]) str str/trim)]
          (if (seq txt) txt {:error "LLM returned empty content"}))))
    (catch Exception e {:error (util/clip (.getMessage e) 200)}))))

(def ^:dynamic *chat* nil)

(defn chat [opts]
  (when-not (fn? *chat*)
    (throw (ex-info "Jukyu inference requires an explicit chat capability"
                    {:capability :jukyu/chat})))
  (*chat* opts))
