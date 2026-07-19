<script lang="ts">
  import { Badge, Button, Card, Chip } from '@etzhayyim/design-system';

  type BalanceRow = {
    country_code: string;
    supply_quantity: number;
    demand_quantity: number;
    balance_quantity: number;
    avg_confidence: number;
  };

  type ChainRow = {
    edge_id: string;
    relationship: string;
    src_node_code: string;
    src_name: string;
    src_country_code: string;
    dst_node_code: string;
    dst_name: string;
    dst_country_code: string;
    product_code: string;
    capacity_quantity: number;
    dependency_weight: number;
    confidence: number;
    status: string;
  };

  type ExposureRow = {
    company_did: string;
    company_name: string;
    country_code: string;
    product_code: string;
    supply_pressure: number;
    demand_pressure: number;
    downstream_pressure: number;
    structural_pressure: number;
    risk_score: number;
    confidence: number;
    recommended_action: string;
  };

  type SignalRow = {
    signalId: string;
    targetCompanyDid: string;
    countryCode: string;
    productCode: string;
    severity: string;
    riskScore: number;
  };

  type GraphNode = {
    id: string;
    country: string;
    x: number;
    y: number;
    kind: string;
  };

  type DomainSnapshot = {
    label: string;
    unit: string;
    balance: BalanceRow[];
    chain: ChainRow[];
    exposures: ExposureRow[];
    nodes: GraphNode[];
    adapterPath: string;
    timeline: [string, string, string];
  };

  const fallbackBalance: BalanceRow[] = [
    { country_code: 'IN', supply_quantity: 14000, demand_quantity: 0, balance_quantity: 14000, avg_confidence: 0.72 },
    { country_code: 'CN', supply_quantity: 7000, demand_quantity: 0, balance_quantity: 7000, avg_confidence: 0.72 },
    { country_code: 'US', supply_quantity: 6500, demand_quantity: 0, balance_quantity: 6500, avg_confidence: 0.72 },
    { country_code: 'KR', supply_quantity: 0, demand_quantity: 5200, balance_quantity: -5200, avg_confidence: 0.72 },
    { country_code: 'JP', supply_quantity: 0, demand_quantity: 3600, balance_quantity: -3600, avg_confidence: 0.72 },
    { country_code: 'SG', supply_quantity: 0, demand_quantity: 0, balance_quantity: 0, avg_confidence: 0.72 },
    { country_code: 'NL', supply_quantity: 0, demand_quantity: 0, balance_quantity: 0, avg_confidence: 0.72 }
  ];

  const fallbackChain: ChainRow[] = [
    {
      edge_id: 'jamnagar-jurong',
      relationship: 'supplies',
      src_node_code: 'JAMNAGAR-NAPH',
      src_name: 'Jamnagar refinery naphtha export',
      src_country_code: 'IN',
      dst_node_code: 'JURONG-NAPH',
      dst_name: 'Jurong naphtha storage terminal',
      dst_country_code: 'SG',
      product_code: 'NAPH-L',
      capacity_quantity: 6000,
      dependency_weight: 1,
      confidence: 0.72,
      status: 'active'
    },
    {
      edge_id: 'jurong-yeosu',
      relationship: 'supplies',
      src_node_code: 'JURONG-NAPH',
      src_name: 'Jurong naphtha storage terminal',
      src_country_code: 'SG',
      dst_node_code: 'YEOSU-C2',
      dst_name: 'Yeosu steam cracker',
      dst_country_code: 'KR',
      product_code: 'NAPH-L',
      capacity_quantity: 4200,
      dependency_weight: 0.7,
      confidence: 0.72,
      status: 'active'
    },
    {
      edge_id: 'baytown-rotterdam',
      relationship: 'exports_to',
      src_node_code: 'BAYTOWN-NAPH',
      src_name: 'Baytown refinery naphtha splitter',
      src_country_code: 'US',
      dst_node_code: 'ARA-NAPH',
      dst_name: 'ARA Rotterdam naphtha hub',
      dst_country_code: 'NL',
      product_code: 'NAPH-H',
      capacity_quantity: 3000,
      dependency_weight: 0.5,
      confidence: 0.72,
      status: 'active'
    },
    {
      edge_id: 'jurong-chiba',
      relationship: 'supplies',
      src_node_code: 'JURONG-NAPH',
      src_name: 'Jurong naphtha storage terminal',
      src_country_code: 'SG',
      dst_node_code: 'CHIBA-C2',
      dst_name: 'Chiba steam cracker',
      dst_country_code: 'JP',
      product_code: 'NAPH-L',
      capacity_quantity: 2800,
      dependency_weight: 0.47,
      confidence: 0.72,
      status: 'active'
    },
    {
      edge_id: 'zhenhai-yeosu',
      relationship: 'backhaul',
      src_node_code: 'ZHENHAI-NAPH',
      src_name: 'Zhenhai refinery naphtha stream',
      src_country_code: 'CN',
      dst_node_code: 'YEOSU-C2',
      dst_name: 'Yeosu steam cracker',
      dst_country_code: 'KR',
      product_code: 'NAPH-H',
      capacity_quantity: 1800,
      dependency_weight: 0.3,
      confidence: 0.72,
      status: 'monitored'
    }
  ];

  const fallbackExposures: ExposureRow[] = [
    {
      company_did: 'did:web:petrochem.etzhayyim.com',
      company_name: 'Chiba steam cracker',
      country_code: 'JP',
      product_code: 'NAPH-L',
      supply_pressure: 1,
      demand_pressure: 0.85,
      downstream_pressure: 0.65,
      structural_pressure: 0.55,
      risk_score: 0.9,
      confidence: 0.72,
      recommended_action: 'Evaluate alternate naphtha supply routes, term coverage, cracker run-rate flexibility, and inventory buffer.'
    },
    {
      company_did: 'did:web:petrochem.etzhayyim.com',
      company_name: 'Yeosu steam cracker',
      country_code: 'KR',
      product_code: 'NAPH-L',
      supply_pressure: 1,
      demand_pressure: 0.85,
      downstream_pressure: 0.65,
      structural_pressure: 0.55,
      risk_score: 0.9,
      confidence: 0.72,
      recommended_action: 'Evaluate alternate naphtha supply routes, term coverage, cracker run-rate flexibility, and inventory buffer.'
    }
  ];

  const fallbackNodeLayout: GraphNode[] = [
    { id: 'JAMNAGAR-NAPH', country: 'IN', x: 115, y: 170, kind: 'refinery' },
    { id: 'ZHENHAI-NAPH', country: 'CN', x: 210, y: 285, kind: 'refinery' },
    { id: 'BAYTOWN-NAPH', country: 'US', x: 110, y: 420, kind: 'refinery' },
    { id: 'JURONG-NAPH', country: 'SG', x: 440, y: 205, kind: 'terminal' },
    { id: 'ARA-NAPH', country: 'NL', x: 465, y: 420, kind: 'terminal' },
    { id: 'CHIBA-C2', country: 'JP', x: 760, y: 165, kind: 'steam_cracker' },
    { id: 'YEOSU-C2', country: 'KR', x: 750, y: 315, kind: 'steam_cracker' }
  ];

  function makeBalance(rows: Array<[string, number, number, number]>): BalanceRow[] {
    return rows.map(([country_code, supply_quantity, demand_quantity, avg_confidence]) => ({
      country_code,
      supply_quantity,
      demand_quantity,
      balance_quantity: supply_quantity - demand_quantity,
      avg_confidence
    }));
  }

  function exposure(company_name: string, country_code: string, product_code: string, risk_score: number, action: string): ExposureRow {
    return {
      company_did: `did:web:${company_name.toLowerCase().replace(/[^a-z0-9]+/g, '-')}.etzhayyim.com`,
      company_name,
      country_code,
      product_code,
      supply_pressure: Math.min(1, risk_score + 0.1),
      demand_pressure: Math.max(0.35, risk_score - 0.05),
      downstream_pressure: Math.max(0.3, risk_score - 0.18),
      structural_pressure: Math.max(0.25, risk_score - 0.28),
      risk_score,
      confidence: 0.68,
      recommended_action: action
    };
  }

  function chain(edge_id: string, relationship: string, src: GraphNode, dst: GraphNode, product_code: string, capacity_quantity: number, dependency_weight: number, status = 'active'): ChainRow {
    return {
      edge_id,
      relationship,
      src_node_code: src.id,
      src_name: `${src.country} ${src.kind.replace('_', ' ')}`,
      src_country_code: src.country,
      dst_node_code: dst.id,
      dst_name: `${dst.country} ${dst.kind.replace('_', ' ')}`,
      dst_country_code: dst.country,
      product_code,
      capacity_quantity,
      dependency_weight,
      confidence: 0.68,
      status
    };
  }

  const crudeNodes: GraphNode[] = [
    { id: 'RAS-TANURA-CRUDE', country: 'SA', x: 120, y: 165, kind: 'export_terminal' },
    { id: 'BASRA-CRUDE', country: 'IQ', x: 160, y: 300, kind: 'export_terminal' },
    { id: 'HOUSTON-CRUDE', country: 'US', x: 120, y: 430, kind: 'export_hub' },
    { id: 'FUJAIRAH-STOR', country: 'AE', x: 420, y: 210, kind: 'storage' },
    { id: 'ROTTERDAM-REF', country: 'NL', x: 470, y: 420, kind: 'refinery' },
    { id: 'KASHIMA-REF', country: 'JP', x: 760, y: 170, kind: 'refinery' },
    { id: 'ULSAN-REF', country: 'KR', x: 750, y: 320, kind: 'refinery' }
  ];

  const lngNodes: GraphNode[] = [
    { id: 'QATAR-NFE', country: 'QA', x: 120, y: 160, kind: 'liquefaction' },
    { id: 'GLADSTONE-LNG', country: 'AU', x: 165, y: 330, kind: 'liquefaction' },
    { id: 'SABINE-LNG', country: 'US', x: 115, y: 430, kind: 'liquefaction' },
    { id: 'SINGAPORE-LNG', country: 'SG', x: 430, y: 245, kind: 'trading_hub' },
    { id: 'ZEEBRUGGE-LNG', country: 'BE', x: 470, y: 425, kind: 'regas' },
    { id: 'TOKYO-BAY-LNG', country: 'JP', x: 760, y: 170, kind: 'regas' },
    { id: 'INCHEON-LNG', country: 'KR', x: 750, y: 320, kind: 'regas' }
  ];

  const copperNodes: GraphNode[] = [
    { id: 'ESCONDIDA-CU', country: 'CL', x: 120, y: 170, kind: 'mine' },
    { id: 'GRASBERG-CU', country: 'ID', x: 190, y: 315, kind: 'mine' },
    { id: 'KAMOA-CU', country: 'CD', x: 130, y: 425, kind: 'mine' },
    { id: 'NINGBO-SMELTER', country: 'CN', x: 430, y: 210, kind: 'smelter' },
    { id: 'HAMBURG-CU', country: 'DE', x: 470, y: 420, kind: 'fabricator' },
    { id: 'OSAKA-WIRE', country: 'JP', x: 760, y: 170, kind: 'fabricator' },
    { id: 'BUSAN-EV-CU', country: 'KR', x: 750, y: 320, kind: 'fabricator' }
  ];

  const lithiumNodes: GraphNode[] = [
    { id: 'ATACAMA-LI', country: 'CL', x: 120, y: 165, kind: 'brine' },
    { id: 'GREENBUSHES-LI', country: 'AU', x: 165, y: 315, kind: 'mine' },
    { id: 'QINGHAI-LI', country: 'CN', x: 210, y: 430, kind: 'brine' },
    { id: 'YIBIN-LFP', country: 'CN', x: 430, y: 220, kind: 'processor' },
    { id: 'GDANSK-CAM', country: 'PL', x: 470, y: 420, kind: 'cathode' },
    { id: 'KANSAI-BATT', country: 'JP', x: 760, y: 170, kind: 'battery' },
    { id: 'POHANG-BATT', country: 'KR', x: 750, y: 320, kind: 'battery' }
  ];

  const wheatNodes: GraphNode[] = [
    { id: 'BLACKSEA-WHT', country: 'UA', x: 120, y: 165, kind: 'grain_export' },
    { id: 'PRAIRIE-WHT', country: 'CA', x: 165, y: 315, kind: 'grain_export' },
    { id: 'FREMANTLE-WHT', country: 'AU', x: 120, y: 430, kind: 'grain_export' },
    { id: 'SUEZ-GRAIN', country: 'EG', x: 430, y: 220, kind: 'transit' },
    { id: 'ROTTERDAM-GRAIN', country: 'NL', x: 470, y: 420, kind: 'terminal' },
    { id: 'YOKOHAMA-MILL', country: 'JP', x: 760, y: 170, kind: 'mill' },
    { id: 'INCHEON-MILL', country: 'KR', x: 750, y: 320, kind: 'mill' }
  ];

  const semiNodes: GraphNode[] = [
    { id: 'TAIWAN-FOUNDRY', country: 'TW', x: 120, y: 165, kind: 'foundry' },
    { id: 'KOREA-MEM', country: 'KR', x: 170, y: 315, kind: 'memory_fab' },
    { id: 'ARIZONA-FAB', country: 'US', x: 120, y: 430, kind: 'fab' },
    { id: 'SHANGHAI-OSAT', country: 'CN', x: 430, y: 220, kind: 'osat' },
    { id: 'DRESDEN-AUTO', country: 'DE', x: 470, y: 420, kind: 'auto_chip' },
    { id: 'KYUSHU-AUTO', country: 'JP', x: 760, y: 170, kind: 'auto_oem' },
    { id: 'AICHI-AUTO', country: 'JP', x: 750, y: 320, kind: 'auto_oem' }
  ];

  const domainSnapshots: Record<string, DomainSnapshot> = {
    naphtha: {
      label: 'Naphtha',
      unit: 'tonnes/day',
      balance: fallbackBalance,
      chain: fallbackChain,
      exposures: fallbackExposures,
      nodes: fallbackNodeLayout,
      adapterPath: '/cron/domain-adapter/naphtha',
      timeline: [
        'naphtha source graph normalized into Jukyu vertex/edge tables',
        'JP and KR deficits propagated through Jurong and Zhenhai lanes',
        'critical MCP notifications emitted by country and product'
      ]
    },
    crude: {
      label: 'Crude oil',
      unit: 'kbpd',
      balance: makeBalance([['SA', 9600, 3200, 0.7], ['IQ', 4200, 850, 0.7], ['US', 5100, 3600, 0.69], ['NL', 900, 1600, 0.66], ['JP', 250, 3100, 0.68], ['KR', 380, 2950, 0.68], ['AE', 0, 0, 0.66]]),
      chain: [
        chain('ras-fujairah', 'ships_to', crudeNodes[0], crudeNodes[3], 'CRUDE-L', 3800, 0.86),
        chain('basra-fujairah', 'ships_to', crudeNodes[1], crudeNodes[3], 'CRUDE-M', 2400, 0.72),
        chain('houston-rotterdam', 'exports_to', crudeNodes[2], crudeNodes[4], 'CRUDE-L', 1700, 0.58),
        chain('fujairah-kashima', 'supplies', crudeNodes[3], crudeNodes[5], 'CRUDE-M', 2100, 0.78),
        chain('fujairah-ulsan', 'supplies', crudeNodes[3], crudeNodes[6], 'CRUDE-L', 2300, 0.8)
      ],
      exposures: [
        exposure('Kashima refinery complex', 'JP', 'CRUDE-M', 0.86, 'Rebalance term crude baskets, hedge freight exposure, and validate refinery slate flexibility.'),
        exposure('Ulsan refinery complex', 'KR', 'CRUDE-L', 0.84, 'Secure alternate Middle East and US Gulf liftings and reserve desulfurization capacity.')
      ],
      nodes: crudeNodes,
      adapterPath: '/cron/domain-adapter/crude',
      timeline: ['crude flow graph aligned from export terminal and refinery nodes', 'Middle East supply pressure propagated into Northeast Asia refinery demand', 'signals target refinery slate, freight, and inventory positions']
    },
    lng: {
      label: 'LNG',
      unit: 'kt/day',
      balance: makeBalance([['QA', 820, 110, 0.7], ['AU', 690, 180, 0.7], ['US', 620, 210, 0.68], ['BE', 120, 180, 0.65], ['JP', 40, 740, 0.68], ['KR', 35, 520, 0.68], ['SG', 0, 0, 0.64]]),
      chain: [
        chain('qatar-singapore', 'ships_to', lngNodes[0], lngNodes[3], 'LNG-SPOT', 310, 0.82),
        chain('gladstone-tokyo', 'supplies', lngNodes[1], lngNodes[5], 'LNG-TERM', 260, 0.76),
        chain('sabine-zeebrugge', 'exports_to', lngNodes[2], lngNodes[4], 'LNG-SPOT', 180, 0.5),
        chain('singapore-tokyo', 'redirects_to', lngNodes[3], lngNodes[5], 'LNG-SPOT', 210, 0.7),
        chain('qatar-incheon', 'supplies', lngNodes[0], lngNodes[6], 'LNG-TERM', 230, 0.72)
      ],
      exposures: [
        exposure('Tokyo Bay LNG regas', 'JP', 'LNG-SPOT', 0.88, 'Prioritize winter cargo cover, storage drawdown plan, and power-sector demand response.'),
        exposure('Incheon LNG regas', 'KR', 'LNG-TERM', 0.81, 'Validate term cargo timing and interruptible industrial gas demand.')
      ],
      nodes: lngNodes,
      adapterPath: '/cron/domain-adapter/lng',
      timeline: ['LNG cargo, regas, and trading hub nodes normalized', 'spot and term cargo constraints propagated into JP/KR power demand', 'signals emitted for winter cover and storage adequacy']
    },
    copper: {
      label: 'Copper',
      unit: 'tonnes/day',
      balance: makeBalance([['CL', 8600, 950, 0.66], ['ID', 3300, 900, 0.64], ['CD', 2900, 600, 0.62], ['CN', 1800, 6200, 0.67], ['DE', 750, 1300, 0.64], ['JP', 420, 1700, 0.65], ['KR', 380, 1550, 0.65]]),
      chain: [
        chain('escondida-ningbo', 'concentrate_to', copperNodes[0], copperNodes[3], 'CU-CONC', 3600, 0.82),
        chain('grasberg-ningbo', 'concentrate_to', copperNodes[1], copperNodes[3], 'CU-CONC', 1900, 0.7),
        chain('kamoa-hamburg', 'concentrate_to', copperNodes[2], copperNodes[4], 'CU-CONC', 1300, 0.55),
        chain('ningbo-osaka', 'cathode_to', copperNodes[3], copperNodes[5], 'CU-CATH', 1250, 0.74),
        chain('ningbo-busan', 'cathode_to', copperNodes[3], copperNodes[6], 'CU-CATH', 1180, 0.72)
      ],
      exposures: [
        exposure('Osaka wire harness cluster', 'JP', 'CU-CATH', 0.79, 'Lock cathode allocations and check substitution options for auto wire harness demand.'),
        exposure('Busan EV copper fabricators', 'KR', 'CU-CATH', 0.77, 'Increase scrap blend analysis and diversify smelter-origin supply.')
      ],
      nodes: copperNodes,
      adapterPath: '/cron/domain-adapter/copper',
      timeline: ['mine, smelter, and fabricator nodes projected into copper graph', 'concentrate and cathode bottlenecks propagated downstream', 'signals target fabricator allocation and scrap substitution']
    },
    lithium: {
      label: 'Lithium',
      unit: 'LCE tonnes/day',
      balance: makeBalance([['AU', 2100, 260, 0.64], ['CL', 1800, 240, 0.64], ['CN', 1200, 2700, 0.66], ['PL', 90, 420, 0.61], ['JP', 40, 680, 0.63], ['KR', 55, 760, 0.63]]),
      chain: [
        chain('greenbushes-yibin', 'spodumene_to', lithiumNodes[1], lithiumNodes[3], 'LI-SPOD', 980, 0.84),
        chain('atacama-yibin', 'carbonate_to', lithiumNodes[0], lithiumNodes[3], 'LI-CARB', 720, 0.74),
        chain('qinghai-yibin', 'carbonate_to', lithiumNodes[2], lithiumNodes[3], 'LI-CARB', 550, 0.62),
        chain('yibin-kansai', 'cathode_to', lithiumNodes[3], lithiumNodes[5], 'LFP-CAM', 360, 0.78),
        chain('yibin-pohang', 'cathode_to', lithiumNodes[3], lithiumNodes[6], 'NCM-CAM', 420, 0.82)
      ],
      exposures: [
        exposure('Kansai battery materials', 'JP', 'LFP-CAM', 0.83, 'Secure conversion tolling capacity and quantify cell-production schedule sensitivity.'),
        exposure('Pohang battery materials', 'KR', 'NCM-CAM', 0.87, 'Diversify precursor/cathode supply and inspect inventory coverage by chemistry.')
      ],
      nodes: lithiumNodes,
      adapterPath: '/cron/domain-adapter/lithium',
      timeline: ['brine, spodumene, processor, and cathode nodes normalized', 'conversion capacity constraints propagated into battery demand', 'signals target chemistry-specific inventory and tolling capacity']
    },
    wheat: {
      label: 'Wheat',
      unit: 'tonnes/day',
      balance: makeBalance([['UA', 9500, 1700, 0.62], ['CA', 7600, 2200, 0.64], ['AU', 6900, 1800, 0.64], ['EG', 300, 6200, 0.61], ['NL', 700, 1400, 0.6], ['JP', 120, 2400, 0.62], ['KR', 90, 1900, 0.62]]),
      chain: [
        chain('blacksea-suez', 'ships_to', wheatNodes[0], wheatNodes[3], 'WHT-MILL', 3900, 0.8),
        chain('prairie-rotterdam', 'exports_to', wheatNodes[1], wheatNodes[4], 'WHT-HARD', 2200, 0.62),
        chain('fremantle-yokohama', 'supplies', wheatNodes[2], wheatNodes[5], 'WHT-NOODLE', 1700, 0.76),
        chain('fremantle-incheon', 'supplies', wheatNodes[2], wheatNodes[6], 'WHT-MILL', 1300, 0.7),
        chain('suez-rotterdam', 'transits_to', wheatNodes[3], wheatNodes[4], 'WHT-MIX', 1100, 0.45)
      ],
      exposures: [
        exposure('Yokohama flour mills', 'JP', 'WHT-NOODLE', 0.74, 'Blend Australian and North American wheat coverage and monitor freight/weather signals.'),
        exposure('Incheon flour mills', 'KR', 'WHT-MILL', 0.72, 'Hedge grain freight and rebalance protein-grade procurement.')
      ],
      nodes: wheatNodes,
      adapterPath: '/cron/domain-adapter/wheat',
      timeline: ['grain export, transit, terminal, and mill nodes normalized', 'weather and route constraints propagated into milling demand', 'signals target flour mill coverage and freight hedge posture']
    },
    semiconductors: {
      label: 'Semiconductors',
      unit: 'wafer-equivalent/day',
      balance: makeBalance([['TW', 7800, 1900, 0.69], ['KR', 5400, 2600, 0.69], ['US', 3300, 2400, 0.66], ['CN', 2100, 5200, 0.65], ['DE', 850, 1600, 0.64], ['JP', 1200, 3900, 0.66]]),
      chain: [
        chain('taiwan-shanghai', 'dies_to', semiNodes[0], semiNodes[3], 'LOGIC-7', 2600, 0.82),
        chain('korea-shanghai', 'memory_to', semiNodes[1], semiNodes[3], 'DRAM', 1900, 0.7),
        chain('arizona-dresden', 'wafers_to', semiNodes[2], semiNodes[4], 'MCU', 1100, 0.55),
        chain('shanghai-kyushu', 'packages_to', semiNodes[3], semiNodes[5], 'AUTO-MCU', 1250, 0.77),
        chain('taiwan-aichi', 'dies_to', semiNodes[0], semiNodes[6], 'AUTO-SoC', 1350, 0.8)
      ],
      exposures: [
        exposure('Kyushu automotive semiconductor demand', 'JP', 'AUTO-MCU', 0.85, 'Prioritize qualified second sources and protect build plans against OSAT interruption.'),
        exposure('Aichi automotive semiconductor demand', 'JP', 'AUTO-SoC', 0.82, 'Map vehicle platform exposure by node and reserve broker-free buffer stock.')
      ],
      nodes: semiNodes,
      adapterPath: '/cron/domain-adapter/semiconductors',
      timeline: ['fab, memory, OSAT, and OEM demand nodes normalized', 'package and advanced-node constraints propagated into auto demand', 'signals target platform-level exposure and second-source readiness']
    }
  };

  const apiBase = import.meta.env.VITE_JUKYU_API_BASE ?? '';

  let selectedDomain = 'naphtha';
  let selectedCountry = 'ALL';
  let activeView = 'Chain';
  let selectedNode = 'CHIBA-C2';
  let balanceRows = fallbackBalance;
  let chainRows = fallbackChain;
  let exposureRows = fallbackExposures;
  let nodeLayout = fallbackNodeLayout;
  let signalRows: SignalRow[] = [];
  let status = 'fallback snapshot';
  let lastRunId = 'local-seed';
  let loading = false;
  let previousDomain = selectedDomain;

  $: currentDomain = domainSnapshots[selectedDomain] ?? domainSnapshots.naphtha;
  $: if (selectedDomain !== previousDomain) {
    const snapshot = currentDomain;
    balanceRows = snapshot.balance;
    chainRows = snapshot.chain;
    exposureRows = snapshot.exposures;
    nodeLayout = snapshot.nodes;
    selectedCountry = 'ALL';
    selectedNode = snapshot.nodes[snapshot.nodes.length - 2]?.id ?? snapshot.nodes[0]?.id ?? '';
    signalRows = [];
    status = `${snapshot.label} fallback snapshot`;
    lastRunId = `${selectedDomain}-seed`;
    previousDomain = selectedDomain;
  }

  $: visibleBalance = selectedCountry === 'ALL'
    ? balanceRows
    : balanceRows.filter((row) => row.country_code === selectedCountry);
  $: visibleExposure = selectedCountry === 'ALL'
    ? exposureRows
    : exposureRows.filter((row) => row.country_code === selectedCountry);
  $: selectedExposure = exposureRows.find((row) => row.country_code === nodeCountry(selectedNode)) ?? exposureRows[0];
  $: totalDeficit = balanceRows
    .filter((row) => row.balance_quantity < 0)
    .reduce((sum, row) => sum + Math.abs(row.balance_quantity), 0);
  $: totalSurplus = balanceRows
    .filter((row) => row.balance_quantity > 0)
    .reduce((sum, row) => sum + row.balance_quantity, 0);
  $: criticalCount = exposureRows.filter((row) => row.risk_score >= 0.8).length;

  function nodeCountry(nodeId: string) {
    return nodeLayout.find((node) => node.id === nodeId)?.country ?? 'ZZ';
  }

  function nodeForCountry(country: string) {
    return nodeLayout.find((node) => node.country === country)?.id ?? nodeLayout[0]?.id ?? selectedNode;
  }

  function riskVariant(score: number) {
    if (score >= 0.8) return 'error';
    if (score >= 0.65) return 'warning';
    return 'success';
  }

  function nodeStress(country: string) {
    const balance = balanceRows.find((row) => row.country_code === country)?.balance_quantity ?? 0;
    if (balance < 0) return 'deficit';
    if (balance > 0) return 'surplus';
    return 'neutral';
  }

  function nodeClass(country: string, id: string) {
    return ['node', nodeStress(country), selectedNode === id ? 'selected' : ''].join(' ');
  }

  function formatTonnes(value: number) {
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
  }

  function formatScore(value: number) {
    return value.toFixed(2);
  }

  async function normalizeDomain() {
    loading = true;
    status = `normalizing ${currentDomain.label} adapter`;
    try {
      const response = await fetch(`${apiBase}${currentDomain.adapterPath}`, { method: 'POST' });
      if (!response.ok) throw new Error(`adapter ${response.status}`);
      const body = await response.json();
      status = `adapter ok: ${body.jukyuSupplyNodesTotal ?? body.supplyNodes ?? 0} nodes`;
    } catch (error) {
      status = `adapter unavailable: ${(error as Error).message}`;
    } finally {
      loading = false;
    }
  }

  async function runEquilibrium() {
    loading = true;
    status = 'running equilibrium';
    try {
      const response = await fetch(`${apiBase}/cron/equilibrium`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          domain: selectedDomain,
          seedCountry: selectedCountry === 'ALL' ? null : selectedCountry,
          riskThreshold: 0.55,
          maxBalanceRows: 25,
          maxChainRows: 50,
          maxExposureRows: 25
        })
      });
      if (!response.ok) throw new Error(`equilibrium ${response.status}`);
      const body = await response.json();
      const result = body.result ?? {};
      balanceRows = result.balanceRows?.length ? result.balanceRows : balanceRows;
      chainRows = result.chainRows?.length ? result.chainRows : chainRows;
      exposureRows = result.exposureRows?.length ? result.exposureRows : exposureRows;
      signalRows = result.signalRows ?? signalRows;
      lastRunId = result.runId ?? lastRunId;
      status = `equilibrium ok: ${result.signalsInserted ?? 0} signals`;
    } catch (error) {
      status = `live endpoint unavailable: ${(error as Error).message}`;
    } finally {
      loading = false;
    }
  }

  async function drainOutbox() {
    loading = true;
    status = 'reading outbox';
    try {
      const response = await fetch(`${apiBase}/cron/outbox-drain`, { method: 'POST' });
      if (!response.ok) throw new Error(`outbox ${response.status}`);
      const body = await response.json();
      status = `outbox ok: ${body.count ?? 0} pending`;
    } catch (error) {
      status = `outbox unavailable: ${(error as Error).message}`;
    } finally {
      loading = false;
    }
  }
</script>

<main class="cockpit">
  <aside class="rail">
    <div class="brand">
      <div class="mark">J</div>
      <div>
        <p class="eyebrow">jukyu.etzhayyim.com</p>
        <h1>Global Balance</h1>
      </div>
    </div>

    <section class="control-group">
      <label for="domain">Domain</label>
      <select id="domain" bind:value={selectedDomain}>
        {#each Object.entries(domainSnapshots) as [value, domain]}
          <option value={value}>{domain.label}</option>
        {/each}
      </select>
    </section>

    <section class="control-group">
      <label for="country">Geography</label>
      <select id="country" bind:value={selectedCountry}>
        <option value="ALL">Global</option>
        {#each balanceRows as row}
          <option value={row.country_code}>{row.country_code}</option>
        {/each}
      </select>
    </section>

    <section class="watchlist">
      <p class="section-title">Watchlist</p>
      {#each exposureRows as exposure}
        <button
          class:active={selectedCountry === exposure.country_code}
          type="button"
          onclick={() => {
            selectedCountry = exposure.country_code;
            selectedNode = nodeForCountry(exposure.country_code);
          }}
        >
          <span>{exposure.company_name}</span>
          <Badge value={formatScore(exposure.risk_score)} variant={riskVariant(exposure.risk_score)} />
        </button>
      {/each}
    </section>

    <section class="status-box">
      <p class="section-title">Agent Loop</p>
      <div class="pulse-line">
        <span class:busy={loading}></span>
        <strong>{status}</strong>
      </div>
      <small>{lastRunId}</small>
    </section>
  </aside>

  <section class="workspace">
    <header class="topbar">
      <div class="tabs" aria-label="Views">
        {#each ['Balance', 'Chain', 'Companies', 'Signals'] as view}
          <Chip label={view} active={activeView === view} onclick={() => (activeView = view)} />
        {/each}
      </div>
      <div class="actions">
        <Button size="sm" variant="outline" onclick={normalizeDomain}>Adapter</Button>
        <Button size="sm" variant="outline" onclick={drainOutbox}>Outbox</Button>
        <Button size="sm" variant="solid-fill" onclick={runEquilibrium}>Run Pregel</Button>
      </div>
    </header>

    <section class="metrics">
      <Card class="metric">
        <span>Global surplus</span>
        <strong>{formatTonnes(totalSurplus)}</strong>
        <small>{currentDomain.unit} available</small>
      </Card>
      <Card class="metric danger">
        <span>Import deficit</span>
        <strong>{formatTonnes(totalDeficit)}</strong>
        <small>{currentDomain.unit} constrained</small>
      </Card>
      <Card class="metric">
        <span>Critical exposure</span>
        <strong>{criticalCount}</strong>
        <small>company-country positions</small>
      </Card>
      <Card class="metric">
        <span>Signals</span>
        <strong>{signalRows.length}</strong>
        <small>current run</small>
      </Card>
    </section>

    <section class="canvas-row">
      <Card class="graph-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">Supply-chain graph</p>
            <h2>{currentDomain.label} propagation</h2>
          </div>
          <Badge value="observed + inferred" variant="accent" />
        </div>

        <svg viewBox="0 0 880 540" role="img" aria-label={`${currentDomain.label} supply chain graph`}>
          <defs>
            <marker id="arrow" markerHeight="10" markerWidth="10" orient="auto" refX="8" refY="3">
              <path d="M0,0 L0,6 L9,3 z" fill="#2563eb" />
            </marker>
            <marker id="arrow-risk" markerHeight="10" markerWidth="10" orient="auto" refX="8" refY="3">
              <path d="M0,0 L0,6 L9,3 z" fill="#dc2626" />
            </marker>
          </defs>

          {#each chainRows as lane}
            {@const source = nodeLayout.find((node) => node.id === lane.src_node_code)}
            {@const target = nodeLayout.find((node) => node.id === lane.dst_node_code)}
            {#if source && target}
              <line
                class:risk-lane={target.country === 'JP' || target.country === 'KR'}
                class="lane"
                x1={source.x}
                x2={target.x}
                y1={source.y}
                y2={target.y}
                stroke-width={2 + lane.dependency_weight * 5}
              />
              <text class="lane-label" x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 10}>
                {lane.product_code} {formatTonnes(lane.capacity_quantity)}
              </text>
            {/if}
          {/each}

          {#each nodeLayout as node}
            <g class={nodeClass(node.country, node.id)} onclick={() => (selectedNode = node.id)} onkeydown={(event) => event.key === 'Enter' && (selectedNode = node.id)} tabindex="0" role="button">
              <circle cx={node.x} cy={node.y} r="32" />
              <text x={node.x} y={node.y - 4}>{node.country}</text>
              <text class="node-code" x={node.x} y={node.y + 15}>{node.id}</text>
            </g>
          {/each}
        </svg>
      </Card>

      <Card class="inspector">
        <p class="eyebrow">Inspector</p>
        <h2>{selectedNode}</h2>
        {#if selectedExposure}
          <div class="risk-score">
            <span>Risk</span>
            <strong>{formatScore(selectedExposure.risk_score)}</strong>
            <Badge value={selectedExposure.country_code} variant={riskVariant(selectedExposure.risk_score)} />
          </div>
          <div class="pressure-grid">
            <span>Supply <b>{formatScore(selectedExposure.supply_pressure)}</b></span>
            <span>Demand <b>{formatScore(selectedExposure.demand_pressure)}</b></span>
            <span>Downstream <b>{formatScore(selectedExposure.downstream_pressure)}</b></span>
            <span>Structural <b>{formatScore(selectedExposure.structural_pressure)}</b></span>
          </div>
          <p class="recommendation">{selectedExposure.recommended_action}</p>
        {:else}
          <p class="recommendation">No company exposure is attached to this node.</p>
        {/if}
      </Card>
    </section>

    <section class="data-grid">
      <Card class="table-panel">
        <div class="panel-heading compact">
          <h2>Balance</h2>
          <Badge value={visibleBalance.length} variant="default" />
        </div>
        <div class="table">
          <div class="tr head"><span>Country</span><span>Supply</span><span>Demand</span><span>Balance</span></div>
          {#each visibleBalance as row}
            <div class:negative={row.balance_quantity < 0} class="tr">
              <span>{row.country_code}</span>
              <span>{formatTonnes(row.supply_quantity)}</span>
              <span>{formatTonnes(row.demand_quantity)}</span>
              <span>{formatTonnes(row.balance_quantity)}</span>
            </div>
          {/each}
        </div>
      </Card>

      <Card class="table-panel">
        <div class="panel-heading compact">
          <h2>Companies</h2>
          <Badge value={visibleExposure.length} variant="default" />
        </div>
        <div class="table company-table">
          <div class="tr head"><span>Company</span><span>Country</span><span>Product</span><span>Risk</span></div>
          {#each visibleExposure as row}
            <button class="tr clickable" type="button" onclick={() => {
              selectedCountry = row.country_code;
              selectedNode = nodeForCountry(row.country_code);
            }}>
              <span>{row.company_name}</span>
              <span>{row.country_code}</span>
              <span>{row.product_code}</span>
              <span>{formatScore(row.risk_score)}</span>
            </button>
          {/each}
        </div>
      </Card>
    </section>

    <section class="timeline">
      <div class="event">
        <span></span>
        <strong>Adapter</strong>
        <small>{currentDomain.timeline[0]}</small>
      </div>
      <div class="event">
        <span></span>
        <strong>Pregel</strong>
        <small>{currentDomain.timeline[1]}</small>
      </div>
      <div class="event">
        <span></span>
        <strong>Signal</strong>
        <small>{currentDomain.timeline[2]}</small>
      </div>
    </section>
  </section>
</main>

<style>
  :global(*) {
    box-sizing: border-box;
  }

  :global(body) {
    margin: 0;
    background: #eef2f7;
    color: #111827;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  :global(button),
  :global(select) {
    font: inherit;
  }

  .cockpit {
    display: grid;
    grid-template-columns: 292px minmax(0, 1fr);
    min-height: 100vh;
  }

  .rail {
    background: #102033;
    color: #f8fafc;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .brand {
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .mark {
    width: 42px;
    height: 42px;
    display: grid;
    place-items: center;
    background: #f97316;
    border-radius: 8px;
    color: white;
    font-weight: 800;
  }

  h1,
  h2,
  p {
    margin: 0;
  }

  h1 {
    font-size: 20px;
    line-height: 1.2;
  }

  h2 {
    font-size: 18px;
    line-height: 1.2;
  }

  .eyebrow,
  .section-title {
    color: #64748b;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
  }

  .rail .eyebrow,
  .rail .section-title {
    color: #93a4b8;
  }

  .control-group {
    display: grid;
    gap: 8px;
  }

  .control-group label {
    font-size: 13px;
    font-weight: 700;
  }

  .control-group select {
    width: 100%;
    min-height: 44px;
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 8px;
    background: #f8fafc;
    color: #111827;
    padding: 0 12px;
  }

  .watchlist {
    display: grid;
    gap: 8px;
  }

  .watchlist button {
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(255, 255, 255, 0.06);
    color: #f8fafc;
    border-radius: 8px;
    min-height: 48px;
    padding: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    text-align: left;
    cursor: pointer;
  }

  .watchlist button.active {
    border-color: #38bdf8;
    background: rgba(56, 189, 248, 0.16);
  }

  .status-box {
    margin-top: auto;
    display: grid;
    gap: 8px;
    padding: 12px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.06);
  }

  .pulse-line {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }

  .pulse-line span {
    width: 9px;
    height: 9px;
    border-radius: 999px;
    background: #22c55e;
  }

  .pulse-line span.busy {
    background: #facc15;
  }

  .status-box small {
    color: #cbd5e1;
    overflow-wrap: anywhere;
  }

  .workspace {
    min-width: 0;
    padding: 18px;
    display: grid;
    gap: 16px;
  }

  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }

  .tabs,
  .actions {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }

  .metrics {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
  }

  :global(.metric) {
    background: white;
    padding: 14px;
    border: 1px solid #d9e2ec;
    border-radius: 8px;
  }

  :global(.metric.danger) {
    border-color: #fecaca;
    background: #fff7f7;
  }

  :global(.metric span),
  :global(.metric small) {
    display: block;
    color: #64748b;
    font-size: 12px;
  }

  :global(.metric strong) {
    display: block;
    margin-top: 6px;
    color: #111827;
    font-size: 26px;
    line-height: 1;
  }

  .canvas-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 340px;
    gap: 12px;
    align-items: stretch;
  }

  :global(.graph-panel),
  :global(.inspector),
  :global(.table-panel) {
    background: white;
    border: 1px solid #d9e2ec;
    border-radius: 8px;
    padding: 14px;
  }

  .panel-heading {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: start;
    margin-bottom: 8px;
  }

  .panel-heading.compact {
    align-items: center;
  }

  svg {
    width: 100%;
    min-height: 360px;
    background: linear-gradient(180deg, #f8fafc, #edf4fb);
    border: 1px solid #d9e2ec;
    border-radius: 8px;
  }

  .lane {
    stroke: #2563eb;
    stroke-linecap: round;
    opacity: 0.62;
    marker-end: url(#arrow);
  }

  .lane.risk-lane {
    stroke: #dc2626;
    opacity: 0.78;
    marker-end: url(#arrow-risk);
  }

  .lane-label {
    fill: #334155;
    font-size: 13px;
    font-weight: 700;
    paint-order: stroke;
    stroke: white;
    stroke-width: 5px;
  }

  .node {
    cursor: pointer;
    outline: none;
  }

  .node circle {
    fill: white;
    stroke: #64748b;
    stroke-width: 3;
  }

  .node.surplus circle {
    stroke: #16a34a;
    fill: #f0fdf4;
  }

  .node.deficit circle {
    stroke: #dc2626;
    fill: #fef2f2;
  }

  .node.selected circle {
    stroke: #f97316;
    stroke-width: 5;
  }

  .node text {
    text-anchor: middle;
    fill: #111827;
    font-size: 14px;
    font-weight: 800;
  }

  .node .node-code {
    font-size: 9px;
    font-weight: 700;
    fill: #475569;
  }

  .inspector {
    display: grid;
    align-content: start;
    gap: 14px;
  }

  .risk-score {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 8px;
    align-items: center;
    padding: 12px;
    background: #f8fafc;
    border-radius: 8px;
  }

  .risk-score strong {
    font-size: 28px;
  }

  .pressure-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .pressure-grid span {
    display: grid;
    gap: 4px;
    background: #f8fafc;
    border-radius: 8px;
    padding: 10px;
    color: #64748b;
    font-size: 12px;
  }

  .pressure-grid b {
    color: #111827;
    font-size: 18px;
  }

  .recommendation {
    color: #334155;
    font-size: 14px;
    line-height: 1.5;
  }

  .data-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }

  .table {
    display: grid;
    gap: 4px;
  }

  .tr {
    display: grid;
    grid-template-columns: 0.8fr 1fr 1fr 1fr;
    gap: 8px;
    align-items: center;
    min-height: 36px;
    padding: 8px;
    border-radius: 6px;
    background: #f8fafc;
    color: #334155;
    font-size: 13px;
  }

  .company-table .tr {
    grid-template-columns: 1.7fr 0.7fr 0.8fr 0.7fr;
  }

  .tr.head {
    background: transparent;
    color: #64748b;
    font-weight: 800;
  }

  .tr.negative {
    background: #fef2f2;
    color: #991b1b;
  }

  .tr.clickable {
    width: 100%;
    border: 0;
    text-align: left;
    cursor: pointer;
  }

  .timeline {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
  }

  .event {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 10px;
    align-items: start;
    background: white;
    border: 1px solid #d9e2ec;
    border-radius: 8px;
    padding: 12px;
  }

  .event span {
    grid-row: span 2;
    width: 10px;
    height: 10px;
    margin-top: 4px;
    border-radius: 999px;
    background: #f97316;
  }

  .event small {
    color: #64748b;
    line-height: 1.4;
  }

  @media (max-width: 980px) {
    .cockpit {
      grid-template-columns: 1fr;
    }

    .rail {
      min-height: auto;
    }

    .canvas-row,
    .data-grid,
    .metrics,
    .timeline {
      grid-template-columns: 1fr;
    }

    .topbar {
      align-items: stretch;
      flex-direction: column;
    }

    svg {
      min-height: 300px;
    }
  }
</style>
