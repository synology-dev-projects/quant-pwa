/**
 * In-Situ Reproduction Test: Options flow tables must show the Trade Date.
 */
import assert from 'node:assert';
import { CockpitView } from '../src/tabs/cockpit_view.js';

console.log('=== Running In-Situ Reproduction Test: Cockpit Flow Table Trade Date ===');

const cockpit = new CockpitView();

const samplePrints = [
  {
    FLOW_ID: 'abc123456789',
    TRADE_DATE: '2026-08-26',
    SYMBOL: 'NVDA',
    ORDER_TYPE: 'BUY_CALL',
    STRIKE_PRICE: 255.0,
    STRIKE_OTM_PCT: 22.0,
    EXPIRATION_DATE: '2026-10-16',
    OPEN_INTEREST: 12900,
    IS_UNUSUAL_OI: 0,
    PREMIUM: 1500000.0,
    NET_SCORE: 0.0
  },
  {
    flow_id: 'def987654321',
    trade_date: '2026-08-27',
    symbol: 'NVDA',
    order_type: 'SELL_PUT',
    strike_price: 170.0,
    strike_otm_pct: -5.0,
    expiration_date: '2026-09-18',
    open_interest: 8500,
    is_unusual_oi: 1,
    premium: 2300000.0,
    net_score: 0.5
  }
];

const markdown = cockpit.buildFlowTableMarkdown(samplePrints);
console.log('Generated Markdown:\n', markdown);

const lines = markdown.split('\n');
const header = lines[0];

// 1. Header verification
assert(
  header.includes('DATE') || header.includes('TRADE DATE'),
  `Header row does not include 'DATE' or 'TRADE DATE': "${header}"`
);

// 2. Row data verification
assert(
  markdown.includes('2026-08-26'),
  `Markdown does not render trade date '2026-08-26'`
);
assert(
  markdown.includes('2026-08-27'),
  `Markdown does not render trade date '2026-08-27'`
);

console.log('✅ Reproduction test passed (Trade Date present)!');
