import { strict as assert } from 'assert';

console.log('==================================================================');
console.log('  PROBING SPX QUANT LEVELS 4-CARD MOVE CONVICTION & MICROSTRUCTURE');
console.log('==================================================================\n');

// 1. Mock browser environment
const _mockStorage = { quant_session_token: 'mock-token' };
global.window = {
  innerWidth: 1024,
  devicePixelRatio: 2,
  location: { origin: 'http://127.0.0.1:8000', hostname: '127.0.0.1', port: '8000' },
  localStorage: {
    getItem: (key) => _mockStorage[key] !== undefined ? _mockStorage[key] : null,
    setItem: (key, val) => { _mockStorage[key] = String(val); },
    removeItem: (key) => { delete _mockStorage[key]; }
  },
  addEventListener: () => {},
  removeEventListener: () => {}
};
global.localStorage = global.window.localStorage;
global.requestAnimationFrame = (cb) => { cb(); return 1; };

global.window.AudioContext = class MockAudioContext {
  constructor() { this.state = 'running'; }
  createGain() { return { gain: { setValueAtTime: () => {} }, connect: () => {} }; }
  createOscillator() { return { frequency: { setValueAtTime: () => {} }, connect: () => {}, start: () => {}, stop: () => {} }; }
  close() { return Promise.resolve(); }
};
global.AudioContext = global.window.AudioContext;

global.Notification = class MockNotification {
  static permission = 'default';
  static requestPermission() { return Promise.resolve('granted'); }
};
global.window.Notification = global.Notification;

global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

function createMockElement(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    id: '',
    className: '',
    value: '',
    textContent: '',
    innerHTML: '',
    style: {},
    children: [],
    parentElement: null,
    appendChild: function(child) {
      this.children.push(child);
      child.parentElement = this;
      return child;
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    setAttribute: (k, v) => { el[k] = v; },
    getAttribute: (k) => el[k] || null,
    querySelector: function(sel) {
      if (sel.startsWith('#')) {
        const id = sel.substring(1);
        if (this.id === id) return this;
      }
      for (const ch of this.children) {
        if (ch.querySelector) {
          const res = ch.querySelector(sel);
          if (res) return res;
        }
      }
      if (this.innerHTML) {
        if (sel.startsWith('#') && this.innerHTML.includes(`id="${sel.substring(1)}"`)) {
          const id = sel.substring(1);
          return { id, className: '', innerHTML: '', style: {}, addEventListener: () => {}, setAttribute: () => {}, querySelector: () => null };
        }
        if (sel.startsWith('.') && this.innerHTML.includes(`class="${sel.substring(1)}`)) {
          return { className: sel.substring(1), innerHTML: '', style: {}, addEventListener: () => {}, setAttribute: () => {}, querySelector: () => null };
        }
      }
      return null;
    },
    querySelectorAll: function() { return []; }
  };
  return el;
}

global.document = {
  createElement: createMockElement,
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  body: createMockElement('body'),
  addEventListener: () => {},
  removeEventListener: () => {}
};

global.fetch = async (url) => {
  if (String(url).includes('/api/quant-levels/dates')) {
    return { ok: true, status: 200, json: async () => ['2026-09-23'] };
  }
  if (String(url).includes('/api/quant-levels/data')) {
    return { ok: true, status: 200, json: async () => ({ status: 'ok', levels: [] }) };
  }
  return { ok: true, status: 200, json: async () => ({}) };
};

// 2. Import LevelsView
const { LevelsView } = await import('../src/tabs/levels_view.js');

const container = createMockElement('div');
const view = new LevelsView();
view.render(container);

// TEST 1: levelsConvictionSection container is mounted in DOM
console.log('--- TEST 1: Conviction Section Mount ---');
assert.ok(container.innerHTML.includes('id="levelsConvictionSection"'), 'levelsConvictionSection container must be in container innerHTML');
assert.ok(container.innerHTML.includes('style="display: none;"'), 'levelsConvictionSection should initially have display: none');
console.log('  ✓ PASS: levelsConvictionSection mounted in initial template\n');

// Mock section element
const mockSection = createMockElement('div');
mockSection.id = 'levelsConvictionSection';
mockSection.style.display = 'none';
container.children.push(mockSection);

// TEST 2: Render 4-Card Conviction Grid with Metrics & Badge
console.log('--- TEST 2: Render 4-Card Grid & Verdict Badge ---');
const sampleConviction = {
  gamma: {
    spot_price: 5700.0,
    zero_gex_level: 5650.0,
    net_gex: 1850000000.0,
    flip_distance_pts: 50.0,
    regime_type: 'POSITIVE_GAMMA',
    regime_label: 'VOL DAMPENED / MEAN REVERTING',
    call_wall: 5750.0,
    put_wall: 5600.0
  },
  internals: {
    rsp_change_pct: 0.69,
    spy_change_pct: 0.44,
    breadth_spread: 0.25,
    nya_change_pct: 0.57,
    breadth_regime: 'BROAD_PARTICIPATION',
    breadth_label: 'BROAD MARKET EXPANSION'
  },
  flow: {
    call_premium: 2300000.0,
    put_premium: 400000.0,
    net_delta_flow: 1900000.0,
    net_delta_bias: 'BULLISH_FLOW',
    aggressor_sweep_pct: 78.5,
    whale_count: 2,
    flow_label: 'AGGRESSIVE CALL ACCUMULATION'
  },
  term_structure: {
    vix_price: 14.5,
    vix9d_price: 13.2,
    ratio: 0.910,
    term_regime: 'CONTANGO',
    term_label: 'CONTANGO (STABLE TREND)'
  },
  composite_score: 85,
  verdict_badge: 'HIGH CONVICTION EXPANSION',
  verdict_explanation: 'Broad market participation supported by contango and institutional call urgency'
};

view.renderConvictionSection(sampleConviction);

assert.strictEqual(mockSection.style.display, 'block', 'Section must be set to display: block when data is present');
assert.ok(mockSection.innerHTML.includes('HIGH CONVICTION EXPANSION'), 'Must render verdict badge');
assert.ok(mockSection.innerHTML.includes('85%'), 'Must render composite score');
assert.ok(mockSection.innerHTML.includes('id="cardGexConviction"'), 'Must render Card 1 (GEX)');
assert.ok(mockSection.innerHTML.includes('id="cardBreadthConviction"'), 'Must render Card 2 (Breadth)');
assert.ok(mockSection.innerHTML.includes('id="cardFlowConviction"'), 'Must render Card 3 (Flow)');
assert.ok(mockSection.innerHTML.includes('id="cardTermStructureConviction"'), 'Must render Card 4 (Term Structure)');
assert.ok(mockSection.innerHTML.includes('+$1.85B'), 'Must format GEX in billions');
assert.ok(mockSection.innerHTML.includes('+0.25%'), 'Must format breadth spread');
assert.ok(mockSection.innerHTML.includes('+$1.9M'), 'Must format net delta flow in millions');
assert.ok(mockSection.innerHTML.includes('0.910'), 'Must format VIX9D/VIX ratio');
console.log('  ✓ PASS: 4 cards, metric rows, and verdict badge rendered correctly\n');

// TEST 3: Graceful Hiding on Null / Incomplete Data
console.log('--- TEST 3: Graceful Hiding on Null Data ---');
view.renderConvictionSection(null);
assert.strictEqual(mockSection.style.display, 'none', 'Section must be hidden when conviction is null');
assert.strictEqual(mockSection.innerHTML, '', 'Section innerHTML must be cleared when conviction is null');
console.log('  ✓ PASS: Graceful hiding verified\n');

// TEST 4: Downside Acceleration / Liquidation Regime
console.log('--- TEST 4: Downside Liquidation & Acceleration Rendering ---');
const panicConviction = {
  gamma: {
    spot_price: 5600.0,
    zero_gex_level: 5660.0,
    net_gex: -2100000000.0,
    flip_distance_pts: -60.0,
    regime_type: 'NEGATIVE_GAMMA',
    regime_label: 'VOL ACCELERATION / EXPANSION',
    call_wall: 5700.0,
    put_wall: 5550.0
  },
  internals: {
    rsp_change_pct: -1.45,
    spy_change_pct: -1.06,
    breadth_spread: -0.39,
    nya_change_pct: -1.55,
    breadth_regime: 'BROAD_SELLING',
    breadth_label: 'BROAD MARKET SELLING'
  },
  flow: {
    call_premium: 300000.0,
    put_premium: 3700000.0,
    net_delta_flow: -3400000.0,
    net_delta_bias: 'BEARISH_FLOW',
    aggressor_sweep_pct: 88.0,
    whale_count: 3,
    flow_label: 'HEAVY PUT ACCUMULATION'
  },
  term_structure: {
    vix_price: 22.0,
    vix9d_price: 25.5,
    ratio: 1.159,
    term_regime: 'BACKWARDATION',
    term_label: 'BACKWARDATION (LIQUIDATION PANIC)'
  },
  composite_score: 92,
  verdict_badge: 'HIGH ACCELERATION TREND',
  verdict_explanation: 'Negative gamma accelerating sell-off with backwardation and broad institutional selling'
};

view.renderConvictionSection(panicConviction);
assert.strictEqual(mockSection.style.display, 'block');
assert.ok(mockSection.innerHTML.includes('HIGH ACCELERATION TREND'), 'Must render HIGH ACCELERATION TREND badge');
assert.ok(mockSection.innerHTML.includes('SHORT GAMMA'), 'Must render SHORT GAMMA pill');
assert.ok(mockSection.innerHTML.includes('-$2.10B'), 'Must render negative GEX');
assert.ok(mockSection.innerHTML.includes('BACKWARDATION'), 'Must render BACKWARDATION regime');
console.log('  ✓ PASS: Downside liquidation regime verified\n');

console.log('==================================================================');
console.log('  ALL 4 DOM TEST SUITES PASSED CLEANLY');
console.log('==================================================================');
