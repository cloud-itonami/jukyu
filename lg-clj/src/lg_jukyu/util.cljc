(ns lg-jukyu.util
  "Shared helpers for the jukyu clj port — timestamps, numeric coercion,
  severity classification, string clipping. JVM/cljs portable."
  (:require [clojure.string :as str])
  #?(:clj (:import [java.time ZonedDateTime ZoneOffset]
                   [java.time.format DateTimeFormatter])))

(defn now-iso
  "Current UTC time as `yyyy-MM-ddTHH:mm:ssZ` (mirrors Python time.strftime gmtime)."
  []
  #?(:clj (.format (DateTimeFormatter/ofPattern "yyyy-MM-dd'T'HH:mm:ss'Z'")
                   (ZonedDateTime/now ZoneOffset/UTC))
     :cljs (.toISOString (js/Date.))))

(defn clip
  "Clip string `s` to at most `n` chars (mirrors Python `str(...)[:n]`)."
  [s n]
  (let [s (str s)] (subs s 0 (min n (count s)))))

(defn clamp [v lo hi] (max lo (min hi v)))

(defn as-int
  "Best-effort int coercion (int | numeric string | else default)."
  [v default]
  (cond
    (integer? v) v
    (number? v)  (long v)
    (string? v)  (try #?(:clj (Long/parseLong (str/trim v))
                         :cljs (let [n (js/parseInt v 10)] (if (js/isNaN n) default n)))
                      (catch #?(:clj Exception :cljs :default) _ default))
    :else        default))

(defn as-float
  [v default]
  (cond
    (number? v) (double v)
    (string? v) (try #?(:clj (Double/parseDouble (str/trim v))
                        :cljs (let [n (js/parseFloat v)] (if (js/isNaN n) default n)))
                     (catch #?(:clj Exception :cljs :default) _ default))
    :else       default))

(defn severity
  "Risk → severity bucket (mirrors the python critical/high/medium/low ladder).
  4-bucket variant used by upsert_signal / run_stress_propagation."
  [risk]
  (let [r (as-float risk 0.0)]
    (cond (>= r 0.8) "critical"
          (>= r 0.6) "high"
          (>= r 0.4) "medium"
          :else      "low")))

(defn severity3
  "3-bucket variant used by the equilibrium loop (critical/high/medium only)."
  [risk]
  (let [r (as-float risk 0.0)]
    (cond (>= r 0.8) "critical"
          (>= r 0.6) "high"
          :else      "medium")))

(defn round4 [x] (/ (Math/round (* (double x) 10000.0)) 10000.0))
