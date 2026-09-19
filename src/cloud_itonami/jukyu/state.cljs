(ns cloud-itonami.jukyu.state
  "App state for the jukyu-ui appview UI of jukyu (etzhayyim-project-jukyu).
  Ported from the former appview/jukyu-ui-jukyu001/svelte/src/App.svelte —
  single-screen operational cockpit: domain selector, geography filter,
  watchlist, agent-loop status, 4 metric cards, SVG supply-chain graph,
  inspector, balance/company tables, 3-step timeline. The Svelte module
  state ($: reactive bindings over selectedDomain / selectedCountry /
  activeView / selectedNode / loading / status) becomes one reagent atom;
  the fallback domain snapshots are carried over verbatim. The three async
  actions (normalizeDomain / runEquilibrium / drainOutbox) POST to the
  same /cron paths and only mutate status/rows — no DB I/O in the edge UI,
  matching the CLAUDE.md UX contract."
  (:require [reagent.core :as r]))

(defn- bal [c s d conf]
  {:country_code c :supply_quantity s :demand_quantity d
   :balance_quantity (- s d) :avg_confidence conf})

(defn- node [id country x y kind]
  {:id id :country country :x x :y y :kind kind})

(defn- chain-row [edge-id rel src dst product cap w & [status]]
  {:edge_id edge-id :relationship rel
   :src_node_code (:id src)
   :src_name (str (:country src) " " (subs (:kind src) 0) )
   :src_country_code (:country src)
   :dst_node_code (:id dst)
   :dst_name (:country dst)
   :dst_country_code (:country dst)
   :product_code product :capacity_quantity cap
   :dependency_weight w :confidence 0.68 :status (or status "active")})

(defn- exposure-row [company country product risk action]
  {:company_did (str "did:web:" company ".etzhayyim.com")
   :company_name company :country_code country :product_code product
   :supply_pressure (min 1 (+ risk 0.1))
   :demand_pressure (max 0.35 (- risk 0.05))
   :downstream_pressure (max 0.3 (- risk 0.18))
   :structural_pressure (max 0.25 (- risk 0.28))
   :risk_score risk :confidence 0.68 :recommended_action action})

;; --- fallback node layouts (verbatim from the Svelte source) ---

(def naphtha-nodes
  [(node "JAMNAGAR-NAPH" "IN" 115 170 "refinery")
   (node "ZHENHAI-NAPH" "CN" 210 285 "refinery")
   (node "BAYTOWN-NAPH" "US" 110 420 "refinery")
   (node "JURONG-NAPH" "SG" 440 205 "terminal")
   (node "ARA-NAPH" "NL" 465 420 "terminal")
   (node "CHIBA-C2" "JP" 760 165 "steam_cracker")
   (node "YEOSU-C2" "KR" 750 315 "steam_cracker")])

(def crude-nodes
  [(node "RAS-TANURA-CRUDE" "SA" 120 165 "export_terminal")
   (node "BASRA-CRUDE" "IQ" 160 300 "export_terminal")
   (node "HOUSTON-CRUDE" "US" 120 430 "export_hub")
   (node "FUJAIRAH-STOR" "AE" 420 210 "storage")
   (node "ROTTERDAM-REF" "NL" 470 420 "refinery")
   (node "KASHIMA-REF" "JP" 760 170 "refinery")
   (node "ULSAN-REF" "KR" 750 320 "refinery")])

(def lng-nodes
  [(node "QATAR-NFE" "QA" 120 160 "liquefaction")
   (node "GLADSTONE-LNG" "AU" 165 330 "liquefaction")
   (node "SABINE-LNG" "US" 115 430 "liquefaction")
   (node "SINGAPORE-LNG" "SG" 430 245 "trading_hub")
   (node "ZEEBRUGGE-LNG" "BE" 470 425 "regas")
   (node "TOKYO-BAY-LNG" "JP" 760 170 "regas")
   (node "INCHEON-LNG" "KR" 750 320 "regas")])

(def copper-nodes
  [(node "ESCONDIDA-CU" "CL" 120 170 "mine")
   (node "GRASBERG-CU" "ID" 190 315 "mine")
   (node "KAMOA-CU" "CD" 130 425 "mine")
   (node "NINGBO-SMELTER" "CN" 430 210 "smelter")
   (node "HAMBURG-CU" "DE" 470 420 "fabricator")
   (node "OSAKA-WIRE" "JP" 760 170 "fabricator")
   (node "BUSAN-EV-CU" "KR" 750 320 "fabricator")])

(def lithium-nodes
  [(node "ATACAMA-LI" "CL" 120 165 "brine")
   (node "GREENBUSHES-LI" "AU" 165 315 "mine")
   (node "QINGHAI-LI" "CN" 210 430 "brine")
   (node "YIBIN-LFP" "CN" 430 220 "processor")
   (node "GDANSK-CAM" "PL" 470 420 "cathode")
   (node "KANSAI-BATT" "JP" 760 170 "battery")
   (node "POHANG-BATT" "KR" 750 320 "battery")])

(def wheat-nodes
  [(node "BLACKSEA-WHT" "UA" 120 165 "grain_export")
   (node "PRAIRIE-WHT" "CA" 165 315 "grain_export")
   (node "FREMANTLE-WHT" "AU" 120 430 "grain_export")
   (node "SUEZ-GRAIN" "EG" 430 220 "transit")
   (node "ROTTERDAM-GRAIN" "NL" 470 420 "terminal")
   (node "YOKOHAMA-MILL" "JP" 760 170 "mill")
   (node "INCHEON-MILL" "KR" 750 320 "mill")])

(def semi-nodes
  [(node "TAIWAN-FOUNDRY" "TW" 120 165 "foundry")
   (node "KOREA-MEM" "KR" 170 315 "memory_fab")
   (node "ARIZONA-FAB" "US" 120 430 "fab")
   (node "SHANGHAI-OSAT" "CN" 430 220 "osat")
   (node "DRESDEN-AUTO" "DE" 470 420 "auto_chip")
   (node "KYUSHU-AUTO" "JP" 760 170 "auto_oem")
   (node "AICHI-AUTO" "JP" 750 320 "auto_oem")])

;; --- fallback rows ---

(def naphtha-balance
  [(bal "IN" 14000 0 0.72) (bal "CN" 7000 0 0.72) (bal "US" 6500 0 0.72)
   (bal "KR" 0 5200 0.72) (bal "JP" 0 3600 0.72) (bal "SG" 0 0 0.72)
   (bal "NL" 0 0 0.72)])

(def naphtha-chain
  [(chain-row "jamnagar-jurong" "supplies" (nth naphtha-nodes 0) (nth naphtha-nodes 3) "NAPH-L" 6000 1)
   (chain-row "jurong-yeosu" "supplies" (nth naphtha-nodes 3) (nth naphtha-nodes 6) "NAPH-L" 4200 0.7)
   (chain-row "baytown-rotterdam" "exports_to" (nth naphtha-nodes 2) (nth naphtha-nodes 4) "NAPH-H" 3000 0.5)
   (chain-row "jurong-chiba" "supplies" (nth naphtha-nodes 3) (nth naphtha-nodes 5) "NAPH-L" 2800 0.47)
   (chain-row "zhenhai-yeosu" "backhaul" (nth naphtha-nodes 1) (nth naphtha-nodes 6) "NAPH-H" 1800 0.3 "monitored")])

(def naphtha-exposures
  [(exposure-row "Chiba steam cracker" "JP" "NAPH-L" 0.9
                 "Evaluate alternate naphtha supply routes, term coverage, cracker run-rate flexibility, and inventory buffer.")
   (exposure-row "Yeosu steam cracker" "KR" "NAPH-L" 0.9
                 "Evaluate alternate naphtha supply routes, term coverage, cracker run-rate flexibility, and inventory buffer.")])

(defn- domain
  "Build one domain snapshot: label, unit, balance rows, chain rows,
  exposures, node layout, adapter path, timeline."
  [label unit balance chain-rows exposures nodes adapter timeline]
  {:label label :unit unit :balance balance :chain chain-rows
   :exposures exposures :nodes nodes :adapter-path adapter :timeline timeline})

(defn- ch [nodes i] (nth nodes i))

(def domains
  (array-map
   :naphtha
   (domain "Naphtha" "tonnes/day" naphtha-balance naphtha-chain naphtha-exposures
           naphtha-nodes "/cron/domain-adapter/naphtha"
           ["naphtha source graph normalized into Jukyu vertex/edge tables"
            "JP and KR deficits propagated through Jurong and Zhenhai lanes"
            "critical MCP notifications emitted by country and product"])

   :crude
   (domain "Crude oil" "kbpd"
           [(bal "SA" 9600 3200 0.7) (bal "IQ" 4200 850 0.7) (bal "US" 5100 3600 0.69)
            (bal "NL" 900 1600 0.66) (bal "JP" 250 3100 0.68) (bal "KR" 380 2950 0.68)
            (bal "AE" 0 0 0.66)]
           [(chain-row "ras-fujairah" "ships_to" (ch crude-nodes 0) (ch crude-nodes 3) "CRUDE-L" 3800 0.86)
            (chain-row "basra-fujairah" "ships_to" (ch crude-nodes 1) (ch crude-nodes 3) "CRUDE-M" 2400 0.72)
            (chain-row "houston-rotterdam" "exports_to" (ch crude-nodes 2) (ch crude-nodes 4) "CRUDE-L" 1700 0.58)
            (chain-row "fujairah-kashima" "supplies" (ch crude-nodes 3) (ch crude-nodes 5) "CRUDE-M" 2100 0.78)
            (chain-row "fujairah-ulsan" "supplies" (ch crude-nodes 3) (ch crude-nodes 6) "CRUDE-L" 2300 0.8)]
           [(exposure-row "Kashima refinery complex" "JP" "CRUDE-M" 0.86
                          "Rebalance term crude baskets, hedge freight exposure, and validate refinery slate flexibility.")
            (exposure-row "Ulsan refinery complex" "KR" "CRUDE-L" 0.84
                          "Secure alternate Middle East and US Gulf liftings and reserve desulfurization capacity.")]
           crude-nodes "/cron/domain-adapter/crude"
           ["crude flow graph aligned from export terminal and refinery nodes"
            "Middle East supply pressure propagated into Northeast Asia refinery demand"
            "signals target refinery slate, freight, and inventory positions"])

   :lng
   (domain "LNG" "kt/day"
           [(bal "QA" 820 110 0.7) (bal "AU" 690 180 0.7) (bal "US" 620 210 0.68)
            (bal "BE" 120 180 0.65) (bal "JP" 40 740 0.68) (bal "KR" 35 520 0.68)
            (bal "SG" 0 0 0.64)]
           [(chain-row "qatar-singapore" "ships_to" (ch lng-nodes 0) (ch lng-nodes 3) "LNG-SPOT" 310 0.82)
            (chain-row "gladstone-tokyo" "supplies" (ch lng-nodes 1) (ch lng-nodes 5) "LNG-TERM" 260 0.76)
            (chain-row "sabine-zeebrugge" "exports_to" (ch lng-nodes 2) (ch lng-nodes 4) "LNG-SPOT" 180 0.5)
            (chain-row "singapore-tokyo" "redirects_to" (ch lng-nodes 3) (ch lng-nodes 5) "LNG-SPOT" 210 0.7)
            (chain-row "qatar-incheon" "supplies" (ch lng-nodes 0) (ch lng-nodes 6) "LNG-TERM" 230 0.72)]
           [(exposure-row "Tokyo Bay LNG regas" "JP" "LNG-SPOT" 0.88
                          "Prioritize winter cargo cover, storage drawdown plan, and power-sector demand response.")
            (exposure-row "Incheon LNG regas" "KR" "LNG-TERM" 0.81
                          "Validate term cargo timing and interruptible industrial gas demand.")]
           lng-nodes "/cron/domain-adapter/lng"
           ["LNG cargo, regas, and trading hub nodes normalized"
            "spot and term cargo constraints propagated into JP/KR power demand"
            "signals emitted for winter cover and storage adequacy"])

   :copper
   (domain "Copper" "tonnes/day"
           [(bal "CL" 8600 950 0.66) (bal "ID" 3300 900 0.64) (bal "CD" 2900 600 0.62)
            (bal "CN" 1800 6200 0.67) (bal "DE" 750 1300 0.64) (bal "JP" 420 1700 0.65)
            (bal "KR" 380 1550 0.65)]
           [(chain-row "escondida-ningbo" "concentrate_to" (ch copper-nodes 0) (ch copper-nodes 3) "CU-CONC" 3600 0.82)
            (chain-row "grasberg-ningbo" "concentrate_to" (ch copper-nodes 1) (ch copper-nodes 3) "CU-CONC" 1900 0.7)
            (chain-row "kamoa-hamburg" "concentrate_to" (ch copper-nodes 2) (ch copper-nodes 4) "CU-CONC" 1300 0.55)
            (chain-row "ningbo-osaka" "cathode_to" (ch copper-nodes 3) (ch copper-nodes 5) "CU-CATH" 1250 0.74)
            (chain-row "ningbo-busan" "cathode_to" (ch copper-nodes 3) (ch copper-nodes 6) "CU-CATH" 1180 0.72)]
           [(exposure-row "Osaka wire harness cluster" "JP" "CU-CATH" 0.79
                          "Lock cathode allocations and check substitution options for auto wire harness demand.")
            (exposure-row "Busan EV copper fabricators" "KR" "CU-CATH" 0.77
                          "Increase scrap blend analysis and diversify smelter-origin supply.")]
           copper-nodes "/cron/domain-adapter/copper"
           ["mine, smelter, and fabricator nodes projected into copper graph"
            "concentrate and cathode bottlenecks propagated downstream"
            "signals target fabricator allocation and scrap substitution"])

   :lithium
   (domain "Lithium" "LCE tonnes/day"
           [(bal "AU" 2100 260 0.64) (bal "CL" 1800 240 0.64) (bal "CN" 1200 2700 0.66)
            (bal "PL" 90 420 0.61) (bal "JP" 40 680 0.63) (bal "KR" 55 760 0.63)]
           [(chain-row "greenbushes-yibin" "spodumene_to" (ch lithium-nodes 1) (ch lithium-nodes 3) "LI-SPOD" 980 0.84)
            (chain-row "atacama-yibin" "carbonate_to" (ch lithium-nodes 0) (ch lithium-nodes 3) "LI-CARB" 720 0.74)
            (chain-row "qinghai-yibin" "carbonate_to" (ch lithium-nodes 2) (ch lithium-nodes 3) "LI-CARB" 550 0.62)
            (chain-row "yibin-kansai" "cathode_to" (ch lithium-nodes 3) (ch lithium-nodes 5) "LFP-CAM" 360 0.78)
            (chain-row "yibin-pohang" "cathode_to" (ch lithium-nodes 3) (ch lithium-nodes 6) "NCM-CAM" 420 0.82)]
           [(exposure-row "Kansai battery materials" "JP" "LFP-CAM" 0.83
                          "Secure conversion tolling capacity and quantify cell-production schedule sensitivity.")
            (exposure-row "Pohang battery materials" "KR" "NCM-CAM" 0.87
                          "Diversify precursor/cathode supply and inspect inventory coverage by chemistry.")]
           lithium-nodes "/cron/domain-adapter/lithium"
           ["brine, spodumene, processor, and cathode nodes normalized"
            "conversion capacity constraints propagated into battery demand"
            "signals target chemistry-specific inventory and tolling capacity"])

   :wheat
   (domain "Wheat" "tonnes/day"
           [(bal "UA" 9500 1700 0.62) (bal "CA" 7600 2200 0.64) (bal "AU" 6900 1800 0.64)
            (bal "EG" 300 6200 0.61) (bal "NL" 700 1400 0.6) (bal "JP" 120 2400 0.62)
            (bal "KR" 90 1900 0.62)]
           [(chain-row "blacksea-suez" "ships_to" (ch wheat-nodes 0) (ch wheat-nodes 3) "WHT-MILL" 3900 0.8)
            (chain-row "prairie-rotterdam" "exports_to" (ch wheat-nodes 1) (ch wheat-nodes 4) "WHT-HARD" 2200 0.62)
            (chain-row "fremantle-yokohama" "supplies" (ch wheat-nodes 2) (ch wheat-nodes 5) "WHT-NOODLE" 1700 0.76)
            (chain-row "fremantle-incheon" "supplies" (ch wheat-nodes 2) (ch wheat-nodes 6) "WHT-MILL" 1300 0.7)
            (chain-row "suez-rotterdam" "transits_to" (ch wheat-nodes 3) (ch wheat-nodes 4) "WHT-MIX" 1100 0.45)]
           [(exposure-row "Yokohama flour mills" "JP" "WHT-NOODLE" 0.74
                          "Blend Australian and North American wheat coverage and monitor freight/weather signals.")
            (exposure-row "Incheon flour mills" "KR" "WHT-MILL" 0.72
                          "Hedge grain freight and rebalance protein-grade procurement.")]
           wheat-nodes "/cron/domain-adapter/wheat"
           ["grain export, transit, terminal, and mill nodes normalized"
            "weather and route constraints propagated into milling demand"
            "signals target flour mill coverage and freight hedge posture"])

   :semiconductors
   (domain "Semiconductors" "wafer-equivalent/day"
           [(bal "TW" 7800 1900 0.69) (bal "KR" 5400 2600 0.69) (bal "US" 3300 2400 0.66)
            (bal "CN" 2100 5200 0.65) (bal "DE" 850 1600 0.64) (bal "JP" 1200 3900 0.66)]
           [(chain-row "taiwan-shanghai" "dies_to" (ch semi-nodes 0) (ch semi-nodes 3) "LOGIC-7" 2600 0.82)
            (chain-row "korea-shanghai" "memory_to" (ch semi-nodes 1) (ch semi-nodes 3) "DRAM" 1900 0.7)
            (chain-row "arizona-dresden" "wafers_to" (ch semi-nodes 2) (ch semi-nodes 4) "MCU" 1100 0.55)
            (chain-row "shanghai-kyushu" "packages_to" (ch semi-nodes 3) (ch semi-nodes 5) "AUTO-MCU" 1250 0.77)
            (chain-row "taiwan-aichi" "dies_to" (ch semi-nodes 0) (ch semi-nodes 6) "AUTO-SoC" 1350 0.8)]
           [(exposure-row "Kyushu automotive semiconductor demand" "JP" "AUTO-MCU" 0.85
                          "Prioritize qualified second sources and protect build plans against OSAT interruption.")
            (exposure-row "Aichi automotive semiconductor demand" "JP" "AUTO-SoC" 0.82
                          "Map vehicle platform exposure by node and reserve broker-free buffer stock.")]
           semi-nodes "/cron/domain-adapter/semiconductors"
           ["fab, memory, OSAT, and OEM demand nodes normalized"
            "package and advanced-node constraints propagated into auto demand"
            "signals target platform-level exposure and second-source readiness"])))

(defonce state
  (r/atom
   {:selected-domain :naphtha
    :selected-country "ALL"
    :active-view "Balance"
    :selected-node "CHIBA-C2"
    :balance-rows naphtha-balance
    :chain-rows naphtha-chain
    :exposure-rows naphtha-exposures
    :node-layout naphtha-nodes
    :signal-rows []
    :status "fallback snapshot"
    :last-run-id "local-seed"
    :loading false}))
;; --- derived selectors (the Svelte $: reactive bindings). Appended to
;; state.cljs at build time by tools/append-selectors; kept in a separate
;; file during authoring because the patch tool cannot match freshly
;; written files in _wt worktrees. ---

(defn- node-country [s node-id]
  (or (:country (some #(when (= (:id %) node-id) %) (:node-layout s))) "ZZ"))

(defn domain-snapshot [s k] (get domains k (get domains :naphtha)))

(defn visible-balance [s]
  (if (= (:selected-country s) "ALL")
    (:balance-rows s)
    (filterv #(= (:country_code %) (:selected-country s)) (:balance-rows s))))

(defn visible-exposure [s]
  (if (= (:selected-country s) "ALL")
    (:exposure-rows s)
    (filterv #(= (:country_code %) (:selected-country s)) (:exposure-rows s))))

(defn selected-exposure [s]
  (let [c (node-country s (:selected-node s))]
    (or (some #(when (= (:country_code %) c) %) (:exposure-rows s))
        (first (:exposure-rows s)))))

(defn total-deficit [s]
  (reduce + 0 (map #(js/Math.abs (:balance_quantity %))
                   (filterv #(neg? (:balance_quantity %)) (:balance-rows s)))))

(defn total-surplus [s]
  (reduce + 0 (map #(:balance_quantity %)
                   (filterv #(pos? (:balance_quantity %)) (:balance-rows s)))))

(defn critical-count [s]
  (count (filterv #(>= (:risk_score %) 0.8) (:exposure-rows s))))

(defn node-stress [s n]
  (let [b (:balance_quantity
           (some #(when (= (:country_code %) (:country n)) %) (:balance-rows s)))]
    (cond (nil? b) ""
          (neg? b) "deficit"
          (pos? b) "surplus"
          :else "")))
