import { describe, it, expect, beforeEach } from "vitest";
import { MockEtzhayyim } from "@etzhayyim/sdk-mock";
import {
  registerSupplyNode,
  getSupplyNode,
  listSupplyNodes,
  recordBalance,
  listBalance,
  recordExposure,
  listExposure,
  getExposure,
  coverage,
} from "../src/index.js";

const OWNER = "did:web:jukyu.etzhayyim.com";

describe("jukyu kotoba (kotoba-E2E split)", () => {
  let e: any;
  beforeEach(() => {
    e = new MockEtzhayyim({ did: OWNER });
  });

  describe("supplyNode (PLAINTEXT public catalog)", () => {
    it("registers, dedups, validates, gets, lists/filters", async () => {
      expect((await registerSupplyNode(e, { nodeCode: "JP-NAPH-01", domain: "naphtha", nodeKind: "refinery", countryCode: "JP", productFamily: "naphtha", supplyCapacity: "1200.5", utilizationPct: 80 })).status).toBe("registered");
      expect((await registerSupplyNode(e, { nodeCode: "JP-NAPH-01", domain: "naphtha", nodeKind: "refinery" })).status).toBe("alreadyExists");
      // invalid: non-decimal capacity string
      expect((await registerSupplyNode(e, { nodeCode: "BAD", domain: "x", nodeKind: "y", supplyCapacity: "1,200" })).status).toBe("rejected");
      // invalid: utilizationPct > 100
      expect((await registerSupplyNode(e, { nodeCode: "BAD2", domain: "x", nodeKind: "y", utilizationPct: 200 })).status).toBe("rejected");
      await registerSupplyNode(e, { nodeCode: "US-OIL-02", domain: "crude_oil", nodeKind: "terminal", countryCode: "US", productFamily: "crude" });
      expect((await listSupplyNodes(e)).total).toBe(2);
      expect((await listSupplyNodes(e, { domain: "naphtha" })).total).toBe(1);
      expect((await listSupplyNodes(e, { countryCode: "US" })).total).toBe(1);
      const got = await getSupplyNode(e, { nodeCode: "JP-NAPH-01" });
      expect(got.node?.supplyCapacity).toBe("1200.5");
      expect(got.node?.utilizationPct).toBe(80);
      expect((await getSupplyNode(e, { nodeCode: "NOPE" })).error).toBe("notFound");
    });
  });

  describe("balanceObservation (PLAINTEXT aggregate + FK)", () => {
    it("records, dedups, validates, enforces FK on nodeCode, lists/filters", async () => {
      await registerSupplyNode(e, { nodeCode: "JP-NAPH-01", domain: "naphtha", nodeKind: "refinery" });
      expect((await recordBalance(e, { observationId: "o1", domain: "naphtha", nodeCode: "JP-NAPH-01", countryCode: "JP", productFamily: "naphtha", supplyQuantity: "900.0", demandQuantity: "1000.0", balanceQuantity: "-100.0", priceUsdUnit: "650.25", confidence: 72 })).status).toBe("recorded");
      expect((await recordBalance(e, { observationId: "o1", domain: "naphtha" })).status).toBe("alreadyExists");
      // FK miss
      expect((await recordBalance(e, { observationId: "oX", domain: "naphtha", nodeCode: "GHOST" })).status).toBe("rejected");
      // invalid decimal
      expect((await recordBalance(e, { observationId: "oY", domain: "naphtha", priceUsdUnit: "abc" })).status).toBe("rejected");
      // invalid confidence
      expect((await recordBalance(e, { observationId: "oZ", domain: "naphtha", confidence: 150 })).status).toBe("rejected");
      await recordBalance(e, { observationId: "o2", domain: "crude_oil", countryCode: "US" });
      expect((await listBalance(e)).total).toBe(2);
      expect((await listBalance(e, { domain: "naphtha" })).total).toBe(1);
    });
  });

  describe("companyExposure (E2E-ENCRYPTED CUI)", () => {
    it("seals via encryptedWrite, round-trips via encryptedRead, validates", async () => {
      const ok = await recordExposure(e, { exposureId: "x1", companyDid: "did:web:acme.example", companyName: "Acme", domain: "naphtha", countryCode: "JP", riskScore: 85, supplyPressure: 70, confidence: 60, recommendedAction: "hedge" });
      expect(ok.status).toBe("recorded");
      expect(ok.keyId).toBeTruthy();
      // riskScore out of 0-100
      expect((await recordExposure(e, { exposureId: "xX", companyDid: "d", domain: "t", riskScore: 200 })).status).toBe("rejected");
      // pressure out of range
      expect((await recordExposure(e, { exposureId: "xY", companyDid: "d", domain: "t", riskScore: 50, demandPressure: 300 })).status).toBe("rejected");
      const got = await getExposure(e, { exposureId: "x1" });
      expect(got.exposure?.companyDid).toBe("did:web:acme.example");
      expect(got.exposure?.riskScore).toBe(85);
      await recordExposure(e, { exposureId: "x2", companyDid: "did:web:globex.example", domain: "crude_oil", riskScore: 40 });
      expect((await listExposure(e)).total).toBe(2);
      expect((await listExposure(e, { domain: "naphtha" })).total).toBe(1);
      // minRiskScore filter
      expect((await listExposure(e, { minRiskScore: 60 })).total).toBe(1);
    });

    it("enforces read-cap: a non-recipient DID cannot decrypt the exposure", async () => {
      await recordExposure(e, { exposureId: "x1", companyDid: "did:web:acme.example", domain: "naphtha", riskScore: 85 });
      const outsider: any = new MockEtzhayyim({ did: "did:web:outsider.example" });
      expect((await listExposure(outsider)).total).toBe(0);
    });

    it("grants read-cap to an explicit recipient", async () => {
      const partner = "did:web:partner.example";
      const r = await recordExposure(e, { exposureId: "x1", companyDid: "did:web:acme.example", domain: "naphtha", riskScore: 85, recipients: [partner] });
      expect(r.status).toBe("recorded");
      expect((await listExposure(e)).total).toBe(1);
    });
  });

  describe("coverage rollup", () => {
    it("counts plaintext nodes + observations + E2E exposures", async () => {
      await registerSupplyNode(e, { nodeCode: "JP-NAPH-01", domain: "naphtha", nodeKind: "refinery" });
      await registerSupplyNode(e, { nodeCode: "JP-NAPH-02", domain: "naphtha", nodeKind: "tank" });
      await registerSupplyNode(e, { nodeCode: "US-OIL-01", domain: "crude_oil", nodeKind: "terminal" });
      await recordBalance(e, { observationId: "o1", domain: "naphtha" });
      await recordExposure(e, { exposureId: "x1", companyDid: "did:web:acme.example", domain: "naphtha", riskScore: 70 });
      const cov = await coverage(e);
      expect(cov.supplyNodeCount).toBe(3);
      expect(cov.balanceObservationCount).toBe(1);
      expect(cov.companyExposureCount).toBe(1);
      expect(cov.nodesByDomain?.naphtha).toBe(2);
      expect(cov.nodesByDomain?.crude_oil).toBe(1);
    });
  });
});
