// jukyu.etzhayyim.com thin edge facade. Equilibrium logic runs in the resident
// LangServer/Pregel loop; this worker serves UI assets and proxies control calls.

interface SecretBinding {
  get(): Promise<string>;
}

interface Env {
  ASSETS?: { fetch(req: Request): Promise<Response> };
  DISPATCHER_URL?: string;
  DISPATCHER_INTERNAL_SECRET?: string | SecretBinding;
  APP_NANOID?: string;
}

interface ExportedHandler<E> {
  fetch(req: Request, env: E): Promise<Response>;
}

const APP = "jukyu";
const NSID_PREFIX = "com.etzhayyim.apps.jukyu.";
const CRON_PATHS = new Set([
  "/cron/equilibrium",
  "/cron/outbox-drain",
]);
const UTIL_PATHS = new Set([
  "/extract/shocks",
  "/export/brief",
]);

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === "/health" || url.pathname === "/healthz" || url.pathname === "/readyz" || url.pathname === "/_app/meta") {
      return json({
        ok: true,
        actor: "did:web:jukyu.etzhayyim.com",
        nanoid: env.APP_NANOID ?? "jukyu001",
        execution: "edge-proxy+agentgateway-mcp+langserver+pregel",
        businessLogic: "com-etzhayyim-jukyu and kotodama resident loop",
        graph: {
          domains: ["naphtha", "crude", "lng", "copper", "lithium", "wheat", "semiconductors"],
          vertex: ["company", "plant", "commodity", "region", "port", "signal"],
          edge: ["supplies", "consumes", "ships_to", "exposed_to", "substitutes"],
          mv: ["mv_jukyu_balance_live", "mv_jukyu_company_exposure", "mv_jukyu_signal_outbox"],
        },
      });
    }

    const nsid = url.pathname.startsWith("/xrpc/") ? url.pathname.slice("/xrpc/".length) : "";
    const isDomainAdapter = /^\/cron\/domain-adapter\/[a-z0-9-]+$/.test(url.pathname);
    if ((nsid.startsWith(NSID_PREFIX) || CRON_PATHS.has(url.pathname) || UTIL_PATHS.has(url.pathname) || isDomainAdapter) && (req.method === "POST" || req.method === "GET")) {
      const body = await bodyWithQuery(req, url);
      if (body.__invalidJson) return json({ error: "InvalidJson" }, 400);
      const target = nsid ? `/xrpc/${nsid}` : url.pathname;
      return proxyToDispatcher(env, target, body);
    }

    if (env.ASSETS) return env.ASSETS.fetch(req);
    return json({ error: "NotFound", message: `${APP} not found` }, 404);
  },
} satisfies ExportedHandler<Env>;

async function bodyWithQuery(req: Request, url: URL): Promise<Record<string, unknown>> {
  let body: Record<string, unknown> = {};
  if (req.method === "POST") {
    const text = await req.text();
    try {
      body = text ? JSON.parse(text) as Record<string, unknown> : {};
    } catch {
      return { __invalidJson: true };
    }
  }
  for (const [key, value] of url.searchParams) if (!(key in body)) body[key] = value;
  return body;
}

async function proxyToDispatcher(env: Env, path: string, body: Record<string, unknown>): Promise<Response> {
  const base = (env.DISPATCHER_URL ?? "https://dispatcher.etzhayyim.com").replace(/\/+$/, "");
  const headers: Record<string, string> = { "content-type": "application/json" };
  const trust = await internalTrustSecret(env);
  if (trust) headers["x-internal-trust"] = trust;
  const resp = await fetch(`${base}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  const text = await resp.text();
  return new Response(text, {
    status: resp.status,
    headers: {
      "content-type": resp.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}

async function internalTrustSecret(env: Env): Promise<string> {
  const binding = env.DISPATCHER_INTERNAL_SECRET;
  if (!binding) return "";
  try {
    return typeof binding === "string" ? binding : await binding.get();
  } catch {
    return "";
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
