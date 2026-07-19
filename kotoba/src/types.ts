/**
 * jukyu kotoba — Global Supply-Demand System, kotoba-E2E split.
 *
 * Per ADR-2606011400 (Consensys) + ADR-2605172400 (3-axis) + ADR-2605181100
 * (kotoba E2E encrypted-record envelope). Founder directive 2026-06-03: PII /
 * CUI / LE / confidential per-company scores migrate to etzhayyim when made safe
 * via kotoba E2E.
 *
 * SPLIT (derived from the actual jukyu graph contract — supply_node /
 * balance_observation / company_exposure / notification_signal):
 *   PUBLIC (plaintext AT records):
 *     - supplyNode: normalized supply/demand node catalog (site/company/product/
 *       country). Public reference/catalog data — domain, code, kind, geography,
 *       product family, capacities. No confidential scoring.
 *     - balanceObservation: aggregate supply/demand/inventory/balance + price
 *       observation by domain×country×product. Market-aggregate metadata, not
 *       subject-confidential.
 *   SENSITIVE / CUI (kotoba E2E, com.etzhayyim.encrypted.record):
 *     - companyExposure: per-COMPANY ranked risk score + pressure breakdown +
 *       recommended action + evidence. Confidential per-subject intelligence
 *       (target-company signal precursor) → sealed via sdk.encryptedWrite,
 *       read-cap = owner DID (+ explicit recipients). The substrate never sees
 *       the per-company risk score in plaintext.
 *
 *   STAYS etzhayyim (consumed via consent-capability — NOT collections):
 *     - Pregel stress-propagation EXECUTION (run_stress_propagation), LLM
 *       INFERENCE (qwen3-30b extraction / gemma-4-e4b-it narrative via
 *       llm.etzhayyim.com), and notification DISPATCH / delivery ACTION
 *       (notifyCompany channel send). These are regulated *acts*; the resulting
 *       DATA records migrate (public plaintext / sensitive E2E).
 *
 * AT-Lexicon: no float. Quantities/prices = decimal STRINGS (DOUBLE PRECISION in
 * the etzhayyim graph → string here to preserve precision). utilization/confidence/
 * risk = integer 0-100.
 */

// Plaintext public collections.
export const SUPPLY_NODE_COLLECTION = "com.etzhayyim.apps.jukyu.supplyNode";
export const BALANCE_OBSERVATION_COLLECTION = "com.etzhayyim.apps.jukyu.balanceObservation";
// E2E inner-type NSID (body shape inside the encrypted envelope).
export const COMPANY_EXPOSURE_INNER_TYPE = "com.etzhayyim.apps.jukyu.companyExposure";

export const JUKYU_DID_PREFIX = "did:web:jukyu.etzhayyim.com:" as const;

// ─── Supply node (PLAINTEXT, public catalog) ────────────────────────

export interface SupplyNodeRecord {
  did: string;
  nodeCode: string;
  domain: string;
  nodeKind: string;
  displayName?: string;
  countryCode?: string;
  productFamily?: string;
  capacityUnit?: string;
  /** decimal string (DOUBLE PRECISION in graph). */
  supplyCapacity?: string;
  /** decimal string. */
  demandCapacity?: string;
  /** integer 0-100. */
  utilizationPct?: number;
  status?: string;
  createdAt: string;
}
export interface SupplyNodeView extends SupplyNodeRecord {
  nodeUri: string;
}
export interface RegisterSupplyNodeInput {
  nodeCode: string;
  domain: string;
  nodeKind: string;
  displayName?: string;
  countryCode?: string;
  productFamily?: string;
  capacityUnit?: string;
  supplyCapacity?: string;
  demandCapacity?: string;
  utilizationPct?: number;
  status?: string;
}
export interface RegisterSupplyNodeOutput {
  status: "registered" | "alreadyExists" | "rejected";
  nodeUri?: string;
  did?: string;
  nodeCode?: string;
  error?: string;
}
export interface GetSupplyNodeInput {
  nodeCode: string;
}
export interface GetSupplyNodeOutput {
  node?: SupplyNodeView;
  error?: string;
}
export interface ListSupplyNodesInput {
  domain?: string;
  countryCode?: string;
  productFamily?: string;
  limit?: number;
  cursor?: string;
}
export interface ListSupplyNodesOutput {
  items: SupplyNodeView[];
  cursor?: string;
  total: number;
}

// ─── Balance observation (PLAINTEXT, market aggregate) ──────────────

export interface BalanceObservationRecord {
  did: string;
  observationId: string;
  domain: string;
  countryCode?: string;
  productFamily?: string;
  /** decimal string. */
  supplyQuantity?: string;
  /** decimal string. */
  demandQuantity?: string;
  /** decimal string. */
  balanceQuantity?: string;
  quantityUnit?: string;
  /** decimal string (USD/unit). */
  priceUsdUnit?: string;
  /** integer 0-100. */
  confidence?: number;
  observedAt: string;
  createdAt: string;
}
export interface BalanceObservationView extends BalanceObservationRecord {
  observationUri: string;
}
export interface RecordBalanceInput {
  observationId: string;
  domain: string;
  /** FK: supplyNode.nodeCode that this observation references (optional). */
  nodeCode?: string;
  countryCode?: string;
  productFamily?: string;
  supplyQuantity?: string;
  demandQuantity?: string;
  balanceQuantity?: string;
  quantityUnit?: string;
  priceUsdUnit?: string;
  confidence?: number;
  observedAt?: string;
}
export interface RecordBalanceOutput {
  status: "recorded" | "alreadyExists" | "rejected";
  observationUri?: string;
  did?: string;
  observationId?: string;
  error?: string;
}
export interface ListBalanceInput {
  domain?: string;
  countryCode?: string;
  productFamily?: string;
  limit?: number;
  cursor?: string;
}
export interface ListBalanceOutput {
  items: BalanceObservationView[];
  cursor?: string;
  total: number;
}

// ─── Company exposure (E2E-ENCRYPTED, CUI) ──────────────────────────

export interface CompanyExposureBody {
  exposureId: string;
  companyDid: string;
  companyName?: string;
  domain: string;
  countryCode?: string;
  productFamily?: string;
  /** integer 0-100. */
  supplyPressure?: number;
  /** integer 0-100. */
  demandPressure?: number;
  /** integer 0-100. */
  pricePressure?: number;
  /** integer 0-100. */
  downstreamPressure?: number;
  /** integer 0-100. */
  riskScore: number;
  /** integer 0-100. */
  confidence?: number;
  recommendedAction?: string;
  assessedAt: string;
}
export interface CompanyExposureView extends CompanyExposureBody {
  uri: string;
  sender: string;
  createdAt: string;
}
export interface RecordExposureInput {
  exposureId: string;
  companyDid: string;
  companyName?: string;
  domain: string;
  countryCode?: string;
  productFamily?: string;
  supplyPressure?: number;
  demandPressure?: number;
  pricePressure?: number;
  downstreamPressure?: number;
  riskScore: number;
  confidence?: number;
  recommendedAction?: string;
  assessedAt?: string;
  /** Extra DIDs to grant read-cap (owner always included). */
  recipients?: string[];
}
export interface RecordExposureOutput {
  status: "recorded" | "rejected";
  uri?: string;
  keyId?: string;
  exposureId?: string;
  error?: string;
}
export interface ListExposureInput {
  domain?: string;
  countryCode?: string;
  /** integer 0-100 — only exposures at or above this risk. */
  minRiskScore?: number;
  limit?: number;
  cursor?: string;
}
export interface ListExposureOutput {
  items: CompanyExposureView[];
  cursor?: string;
  total: number;
}
export interface GetExposureInput {
  exposureId: string;
}
export interface GetExposureOutput {
  exposure?: CompanyExposureView;
  error?: string;
}

// ─── Coverage rollup ────────────────────────────────────────────────

export interface CoverageInput {
  maxScan?: number;
}
export interface CoverageOutput {
  supplyNodeCount?: number;
  balanceObservationCount?: number;
  companyExposureCount?: number;
  nodesByDomain?: Record<string, number>;
  truncated?: boolean;
  error?: string;
}

// ─── Validation + helpers ───────────────────────────────────────────

export function isPct(n: unknown): n is number {
  return typeof n === "number" && Number.isInteger(n) && n >= 0 && n <= 100;
}
export function isPctOpt(n: unknown): boolean {
  return n === undefined || isPct(n);
}
/** decimal string: optional sign, digits, optional fractional part. */
export function isDecimalStr(s: unknown): s is string {
  return typeof s === "string" && /^-?\d+(\.\d+)?$/.test(s);
}
export function isDecimalStrOpt(s: unknown): boolean {
  return s === undefined || isDecimalStr(s);
}
export function nodeDidFor(code: string): string {
  return `${JUKYU_DID_PREFIX}node:${code.toLowerCase()}`;
}
export function balanceDidFor(id: string): string {
  return `${JUKYU_DID_PREFIX}obs:${id.toLowerCase()}`;
}
export function slugRkey(prefix: string, id: string): string {
  return `${prefix}-${id.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}
