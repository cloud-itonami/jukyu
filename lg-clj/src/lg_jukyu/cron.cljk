(ns lg-jukyu.cron
  "Cron schedule for lg-jukyu — clj port of `cron.py` + the `crons` array in
  langgraph.json (ADR-2606280030).

  The Python version registers APScheduler jobs read from langgraph.json. Under
  bb there is no in-process scheduler dependency; this ns instead carries the
  cron SPECS as data (kept byte-faithful to langgraph.json) and a `fire!` helper
  that invokes the named graph with its base input. Residency (a real scheduler /
  launchd LaunchAgent) is a deployment-layer concern — the live FastAPI pod keeps
  its APScheduler crons running and COEXISTS."
  (:require [langgraph.graph :as g]
            [lg-jukyu.server :as server]))

(def cron-specs
  "Mirrors langgraph.json `crons` (graph · schedule · input)."
  [{:graph "equilibrium"               :schedule "*/15 * * * *" :input {:with_llm false}}
   {:graph "normalize_domain_adapter"  :schedule "7 * * * *"    :input {:domain "naphtha"}}
   {:graph "normalize_domain_adapter"  :schedule "17 * * * *"   :input {:domain "crude_oil"}}
   {:graph "normalize_domain_adapter"  :schedule "27 */2 * * *" :input {:domain "energy"}}
   {:graph "normalize_domain_adapter"  :schedule "37 */2 * * *" :input {:domain "food"}}
   {:graph "normalize_domain_adapter"  :schedule "47 */3 * * *" :input {:domain "metals"}}
   {:graph "normalize_domain_adapter"  :schedule "57 */3 * * *" :input {:domain "logistics"}}
   {:graph "normalize_domain_adapter"  :schedule "3 */6 * * *"  :input {:domain "transport"}}])

(def ^:dynamic *enabled?*
  "Host-supplied scheduler policy."
  true)

(defn cron-enabled? [] (true? *enabled?*))

(defn fire!
  "Invoke a cron spec's graph with its base input (mirrors `_make_fire`).
  Returns the graph output, or {:error ...} if the graph is unknown."
  [{:keys [graph input]}]
  (if-let [gr (get server/GRAPHS graph)]
    (g/invoke gr (or input {}))
    {:error (str "unknown graph: " graph)}))
