(ns lg-jukyu.audit
  "Fire-and-forget BPMN `generic.audit.emit` shim — clj port of
  `lg/lg_jukyu/audit.py` (ADR-2606280030).

  The Python version POSTs to the in-cluster bpmn-dispatcher as a detached
  asyncio task (best-effort, never fatal). This port keeps the audit edge
  INJECTABLE via `*audit-sink*` (default: no-op, parity with the fire-and-forget
  semantics) so graphs verify under bb without a dispatcher. Wiring the sink to
  a real dispatcher (babashka.http-client) is a deployment-layer concern — the
  Python pod remains the live audit emitter and COEXISTS."
  )

(def app-did "did:web:jukyu.etzhayyim.com")
(def ^:dynamic *app-did* app-did)
(def ^:dynamic *disabled?* false)

(def ^:dynamic *audit-sink*
  "Injectable audit sink. Default: no-op. Contract: (event-map) -> any.
  event-map = {:actor :activity :objectId :objectType :attributes}."
  (fn [_event] nil))

(defn emit-audit
  "Mirror of emit_audit_bg: build the BPMN event and hand it to `*audit-sink*`.
  Returns nil (fire-and-forget). Honours LG_AUDIT_DISABLED=1."
  [{:keys [actor activity object-id object-type attributes]}]
  (when-not *disabled?*
    (try
      (*audit-sink* {:actor      (or actor *app-did*)
                     :activity   activity
                     :objectId   object-id
                     :objectType object-type
                     :attributes (or attributes {})})
      (catch Exception _ nil)))
  nil)
