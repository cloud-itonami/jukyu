/**
 * jukyu kotoba registry — kotoba-E2E split.
 *
 * Plaintext path (supplyNode, balanceObservation): sdk.write / sdk.read —
 * public catalog + market aggregates. FK via exists() on supplyNode.
 * E2E path (companyExposure): sdk.encryptedWrite / sdk.encryptedRead — per-
 * company confidential risk sealed in the kotoba envelope (ADR-2605181100),
 * read-cap = owner DID. The substrate never sees the score in plaintext.
 *
 * STAYS etzhayyim (consent-capability): Pregel propagation EXECUTION, LLM INFERENCE,
 * notification DISPATCH ACTION. Only the EXECUTION stays etzhayyim; data migrates.
 */

import type { Etzhayyim } from "@etzhayyim/sdk";
import {
  BALANCE_OBSERVATION_COLLECTION,
  COMPANY_EXPOSURE_INNER_TYPE,
  SUPPLY_NODE_COLLECTION,
  balanceDidFor,
  isDecimalStrOpt,
  isPct,
  isPctOpt,
  nodeDidFor,
  slugRkey,
  type BalanceObservationRecord,
  type BalanceObservationView,
  type CompanyExposureBody,
  type CompanyExposureView,
  type CoverageInput,
  type CoverageOutput,
  type GetExposureInput,
  type GetExposureOutput,
  type GetSupplyNodeInput,
  type GetSupplyNodeOutput,
  type ListBalanceInput,
  type ListBalanceOutput,
  type ListExposureInput,
  type ListExposureOutput,
  type ListSupplyNodesInput,
  type ListSupplyNodesOutput,
  type RecordBalanceInput,
  type RecordBalanceOutput,
  type RecordExposureInput,
  type RecordExposureOutput,
  type RegisterSupplyNodeInput,
  type RegisterSupplyNodeOutput,
  type SupplyNodeRecord,
  type SupplyNodeView,
} from "./types.js";

const PAGE_LIMIT = 100;
const DEFAULT_MAX_SCAN = 10_000;

// ─── Supply node (PLAINTEXT catalog) ────────────────────────────────

export async function registerSupplyNode(e: Etzhayyim, input: RegisterSupplyNodeInput): Promise<RegisterSupplyNodeOutput> {
  if (!input.nodeCode || !input.domain || !input.nodeKind) return { status: "rejected", error: "missingRequiredFields" };
  if (!isDecimalStrOpt(input.supplyCapacity) || !isDecimalStrOpt(input.demandCapacity)) return { status: "rejected", error: "invalidCapacity" };
  if (!isPctOpt(input.utilizationPct)) return { status: "rejected", error: "invalidUtilizationPct" };
  const rkey = slugRkey("node", input.nodeCode);
  const existing = await e.read<SupplyNodeRecord>({ collection: SUPPLY_NODE_COLLECTION, rkey }).catch(() => ({ records: [] }));
  if (existing.records[0]?.value) {
    return { status: "alreadyExists", nodeUri: existing.records[0].uri, did: existing.records[0].value.did, nodeCode: input.nodeCode };
  }
  const now = new Date().toISOString();
  const did = nodeDidFor(input.nodeCode);
  const record: SupplyNodeRecord = {
    did,
    nodeCode: input.nodeCode,
    domain: input.domain,
    nodeKind: input.nodeKind,
    displayName: input.displayName,
    countryCode: input.countryCode,
    productFamily: input.productFamily,
    capacityUnit: input.capacityUnit,
    supplyCapacity: input.supplyCapacity,
    demandCapacity: input.demandCapacity,
    utilizationPct: input.utilizationPct,
    status: input.status,
    createdAt: now,
  };
  const receipt = await e.write({ collection: SUPPLY_NODE_COLLECTION, record: record as unknown as Record<string, unknown>, rkey });
  return { status: "registered", nodeUri: receipt.uri, did, nodeCode: input.nodeCode };
}

export async function getSupplyNode(e: Etzhayyim, input: GetSupplyNodeInput): Promise<GetSupplyNodeOutput> {
  if (!input.nodeCode) return { error: "invalidNodeCode" };
  const rkey = slugRkey("node", input.nodeCode);
  const resp = await e.read<SupplyNodeRecord>({ collection: SUPPLY_NODE_COLLECTION, rkey }).catch(() => ({ records: [] }));
  const r = resp.records[0];
  if (!r?.value) return { error: "notFound" };
  return { node: { ...r.value, nodeUri: r.uri } };
}

/** FK existence check used by balance observations. */
async function supplyNodeExists(e: Etzhayyim, nodeCode: string): Promise<boolean> {
  const rkey = slugRkey("node", nodeCode);
  const resp = await e.read<SupplyNodeRecord>({ collection: SUPPLY_NODE_COLLECTION, rkey }).catch(() => ({ records: [] }));
  return Boolean(resp.records[0]?.value);
}

export async function listSupplyNodes(e: Etzhayyim, input: ListSupplyNodesInput = {}): Promise<ListSupplyNodesOutput> {
  const limit = Math.min(input.limit ?? 50, 200);
  const resp = await e.read<SupplyNodeRecord>({ collection: SUPPLY_NODE_COLLECTION, cursor: input.cursor, limit });
  const items: SupplyNodeView[] = resp.records
    .filter((r) => !input.domain || r.value.domain === input.domain)
    .filter((r) => !input.countryCode || r.value.countryCode === input.countryCode)
    .filter((r) => !input.productFamily || r.value.productFamily === input.productFamily)
    .map((r) => ({ ...r.value, nodeUri: r.uri }));
  return { items, cursor: resp.cursor, total: items.length };
}

// ─── Balance observation (PLAINTEXT aggregate) ──────────────────────

export async function recordBalance(e: Etzhayyim, input: RecordBalanceInput): Promise<RecordBalanceOutput> {
  if (!input.observationId || !input.domain) return { status: "rejected", error: "missingRequiredFields" };
  if (!isDecimalStrOpt(input.supplyQuantity) || !isDecimalStrOpt(input.demandQuantity) || !isDecimalStrOpt(input.balanceQuantity) || !isDecimalStrOpt(input.priceUsdUnit)) {
    return { status: "rejected", error: "invalidQuantity" };
  }
  if (!isPctOpt(input.confidence)) return { status: "rejected", error: "invalidConfidence" };
  // FK: if a referenced supply node is named, it must exist.
  if (input.nodeCode && !(await supplyNodeExists(e, input.nodeCode))) {
    return { status: "rejected", error: "unknownNodeCode" };
  }
  const rkey = slugRkey("obs", input.observationId);
  const existing = await e.read<BalanceObservationRecord>({ collection: BALANCE_OBSERVATION_COLLECTION, rkey }).catch(() => ({ records: [] }));
  if (existing.records[0]?.value) {
    return { status: "alreadyExists", observationUri: existing.records[0].uri, did: existing.records[0].value.did, observationId: input.observationId };
  }
  const now = new Date().toISOString();
  const did = balanceDidFor(input.observationId);
  const record: BalanceObservationRecord = {
    did,
    observationId: input.observationId,
    domain: input.domain,
    countryCode: input.countryCode,
    productFamily: input.productFamily,
    supplyQuantity: input.supplyQuantity,
    demandQuantity: input.demandQuantity,
    balanceQuantity: input.balanceQuantity,
    quantityUnit: input.quantityUnit,
    priceUsdUnit: input.priceUsdUnit,
    confidence: input.confidence,
    observedAt: input.observedAt ?? now,
    createdAt: now,
  };
  const receipt = await e.write({ collection: BALANCE_OBSERVATION_COLLECTION, record: record as unknown as Record<string, unknown>, rkey });
  return { status: "recorded", observationUri: receipt.uri, did, observationId: input.observationId };
}

export async function listBalance(e: Etzhayyim, input: ListBalanceInput = {}): Promise<ListBalanceOutput> {
  const limit = Math.min(input.limit ?? 50, 200);
  const resp = await e.read<BalanceObservationRecord>({ collection: BALANCE_OBSERVATION_COLLECTION, cursor: input.cursor, limit });
  const items: BalanceObservationView[] = resp.records
    .filter((r) => !input.domain || r.value.domain === input.domain)
    .filter((r) => !input.countryCode || r.value.countryCode === input.countryCode)
    .filter((r) => !input.productFamily || r.value.productFamily === input.productFamily)
    .map((r) => ({ ...r.value, observationUri: r.uri }));
  return { items, cursor: resp.cursor, total: items.length };
}

// ─── Company exposure (E2E-ENCRYPTED, CUI) ──────────────────────────

export async function recordExposure(e: Etzhayyim, input: RecordExposureInput): Promise<RecordExposureOutput> {
  if (!input.exposureId || !input.companyDid || !input.domain) return { status: "rejected", error: "missingRequiredFields" };
  if (!isPct(input.riskScore)) return { status: "rejected", error: "invalidRiskScore" };
  if (!isPctOpt(input.supplyPressure) || !isPctOpt(input.demandPressure) || !isPctOpt(input.pricePressure) || !isPctOpt(input.downstreamPressure) || !isPctOpt(input.confidence)) {
    return { status: "rejected", error: "invalidPressure" };
  }
  const body: CompanyExposureBody = {
    exposureId: input.exposureId,
    companyDid: input.companyDid,
    companyName: input.companyName,
    domain: input.domain,
    countryCode: input.countryCode,
    productFamily: input.productFamily,
    supplyPressure: input.supplyPressure,
    demandPressure: input.demandPressure,
    pricePressure: input.pricePressure,
    downstreamPressure: input.downstreamPressure,
    riskScore: input.riskScore,
    confidence: input.confidence,
    recommendedAction: input.recommendedAction,
    assessedAt: input.assessedAt ?? new Date().toISOString(),
  };
  // Read-cap = owner DID (sender, auto-wrapped) + any explicit recipients.
  const receipt = await e.encryptedWrite<Record<string, unknown>>({
    innerType: COMPANY_EXPOSURE_INNER_TYPE,
    record: body as unknown as Record<string, unknown>,
    recipients: input.recipients ?? [],
    rkey: slugRkey("exposure", input.exposureId),
  });
  return { status: "recorded", uri: receipt.uri, keyId: receipt.keyId, exposureId: input.exposureId };
}

async function scanExposures(e: Etzhayyim, maxScan: number): Promise<CompanyExposureView[]> {
  const out: CompanyExposureView[] = [];
  let cursor: string | undefined;
  while (out.length < maxScan) {
    const page = await e.encryptedRead<CompanyExposureBody>({ innerType: COMPANY_EXPOSURE_INNER_TYPE, cursor, limit: PAGE_LIMIT });
    for (const r of page.records) {
      out.push({ ...r.value, uri: r.uri, sender: r.sender, createdAt: r.createdAt });
    }
    if (!page.cursor || page.records.length === 0) break;
    cursor = page.cursor;
  }
  return out;
}

export async function listExposure(e: Etzhayyim, input: ListExposureInput = {}): Promise<ListExposureOutput> {
  const limit = Math.min(input.limit ?? 50, 200);
  const all = await scanExposures(e, DEFAULT_MAX_SCAN);
  const filtered = all
    .filter((c) => !input.domain || c.domain === input.domain)
    .filter((c) => !input.countryCode || c.countryCode === input.countryCode)
    .filter((c) => input.minRiskScore === undefined || c.riskScore >= input.minRiskScore);
  return { items: filtered.slice(0, limit), total: filtered.length };
}

export async function getExposure(e: Etzhayyim, input: GetExposureInput): Promise<GetExposureOutput> {
  if (!input.exposureId) return { error: "invalidExposureId" };
  const all = await scanExposures(e, DEFAULT_MAX_SCAN);
  const found = all.find((c) => c.exposureId === input.exposureId);
  if (!found) return { error: "notFound" };
  return { exposure: found };
}

// ─── Coverage rollup ────────────────────────────────────────────────

export async function coverage(e: Etzhayyim, input: CoverageInput = {}): Promise<CoverageOutput> {
  const maxScan = Math.min(input.maxScan ?? DEFAULT_MAX_SCAN, DEFAULT_MAX_SCAN);
  const nodesByDomain: Record<string, number> = {};
  let supplyNodeCount = 0;
  let cursor: string | undefined;
  while (supplyNodeCount < maxScan) {
    const page = await e.read<SupplyNodeRecord>({ collection: SUPPLY_NODE_COLLECTION, cursor, limit: PAGE_LIMIT });
    for (const r of page.records) {
      nodesByDomain[r.value.domain] = (nodesByDomain[r.value.domain] ?? 0) + 1;
      supplyNodeCount += 1;
    }
    if (!page.cursor || page.records.length < PAGE_LIMIT) break;
    cursor = page.cursor;
  }
  let balanceObservationCount = 0;
  let balCursor: string | undefined;
  while (balanceObservationCount < maxScan) {
    const page = await e.read<BalanceObservationRecord>({ collection: BALANCE_OBSERVATION_COLLECTION, cursor: balCursor, limit: PAGE_LIMIT });
    balanceObservationCount += page.records.length;
    if (!page.cursor || page.records.length < PAGE_LIMIT) break;
    balCursor = page.cursor;
  }
  const companyExposureCount = (await scanExposures(e, maxScan)).length;
  return {
    supplyNodeCount,
    balanceObservationCount,
    companyExposureCount,
    nodesByDomain,
    truncated: supplyNodeCount >= maxScan || balanceObservationCount >= maxScan || companyExposureCount >= maxScan,
  };
}
