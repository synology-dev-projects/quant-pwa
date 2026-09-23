import { strict as assert } from 'assert';

console.log('==================================================================');
console.log('  PROBING SPX QUANT LEVELS CROSS-ASSET MACRO CORRELATION RIBBON');
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
      // Simple innerHTML substring search for mocked elements
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

// TEST 1: Macro ribbon container is mounted in DOM
console.log('--- TEST 1: Macro Ribbon Container Mount ---');
assert.ok(container.innerHTML.includes('id="levelsMacroRibbon"'), 'levelsMacroRibbon container must be in container innerHTML');
assert.ok(container.innerHTML.includes('style="display: none;"'), 'levelsMacroRibbon should initially have display: none');
console.log('  ✓ PASS: levelsMacroRibbon mounted in initial template');

// Create mock ribbon element
const mockRibbon = createMockElement('div');
mockRibbon.id = 'levelsMacroRibbon';
mockRibbon.style.display = 'none';
container.children.push(mockRibbon);

// TEST 2: Render Bullish Risk-On Macro Context
console.log('\n--- TEST 2: Bullish Risk-On Macro Context ---');
const bullishMacro = {
  vix: {
    symbol: '^VIX',
    label: 'VIX',
    price: 13.20,
    change: -0.45,
    change_pct: -3.3,
    regime_tag: 'EXTREME COMPRESSION',
    sentiment: 'BULLISH',
    updated_at: '2026-09-23T12:00:00Z'
  },
  us10y: {
    symbol: '^TNX',
    label: '10Y YIELD',
    price: 4.125,
    change: -0.010,
    change_pct: -0.24,
    regime_tag: 'YIELD STABLE / NEUTRAL',
    sentiment: 'NEUTRAL',
    updated_at: '2026-09-23T12:00:00Z'
  },
  composite_regime: 'Vol compressed & yields supportive; favorable for equity expansion',
  spx_reaction: 'BULLISH_SUPPORTIVE',
  reaction_label: 'RISK-ON TAILWINDS'
};

view.renderMacroRibbon(bullishMacro);
assert.strictEqual(mockRibbon.style.display, 'flex', 'Ribbon should be flex display when macro context provided');
assert.ok(mockRibbon.innerHTML.includes('id="macroVixPill"'), 'VIX pill should be rendered');
assert.ok(mockRibbon.innerHTML.includes('13.20'), 'VIX pill should display 13.20');
assert.ok(mockRibbon.innerHTML.includes('EXTREME COMPRESSION'), 'VIX pill should display EXTREME COMPRESSION');
assert.ok(mockRibbon.innerHTML.includes('class="macro-regime-badge bullish"'), 'VIX badge should have bullish class');
console.log('  ✓ PASS: VIX pill correctly renders with bullish compression styling');

assert.ok(mockRibbon.innerHTML.includes('id="macro10yPill"'), '10Y pill should be rendered');
assert.ok(mockRibbon.innerHTML.includes('4.125%'), '10Y pill should display yield 4.125%');
assert.ok(mockRibbon.innerHTML.includes('YIELD STABLE / NEUTRAL'), '10Y pill should display yield stable tag');
assert.ok(mockRibbon.innerHTML.includes('class="macro-regime-badge neutral"'), '10Y badge should have neutral class');
console.log('  ✓ PASS: 10Y Yield pill correctly renders with yield value and stable badge');

assert.ok(mockRibbon.innerHTML.includes('id="macroReactionChip"'), 'Reaction chip should be rendered');
assert.ok(mockRibbon.innerHTML.includes('class="macro-reaction-chip bullish"'), 'Reaction chip should have bullish class');
assert.ok(mockRibbon.innerHTML.includes('RISK-ON TAILWINDS'), 'Reaction chip should display RISK-ON TAILWINDS');
console.log('  ✓ PASS: SPX Reaction chip displays RISK-ON TAILWINDS with bullish styling');

// TEST 3: Render Bearish Dual Headwinds Macro Context
console.log('\n--- TEST 3: Bearish Dual Headwinds Macro Context ---');
const bearishMacro = {
  vix: {
    symbol: '^VIX',
    label: 'VIX',
    price: 24.50,
    change: 2.30,
    change_pct: 10.4,
    regime_tag: 'HIGH VOLATILITY (SPIKING)',
    sentiment: 'BEARISH',
    updated_at: '2026-09-23T12:00:00Z'
  },
  us10y: {
    symbol: '^TNX',
    label: '10Y YIELD',
    price: 4.450,
    change: 0.080,
    change_pct: 1.83,
    regime_tag: 'YIELD SURGING / HEADWIND',
    sentiment: 'BEARISH',
    updated_at: '2026-09-23T12:00:00Z'
  },
  composite_regime: 'Vol expanding with surging yields; dual cross-asset headwind',
  spx_reaction: 'BEARISH_PRESSURE',
  reaction_label: 'CROSS-ASSET HEADWINDS'
};

view.renderMacroRibbon(bearishMacro);
assert.ok(mockRibbon.innerHTML.includes('class="macro-reaction-chip bearish"'), 'Reaction chip should have bearish class');
assert.ok(mockRibbon.innerHTML.includes('CROSS-ASSET HEADWINDS'), 'Reaction chip should display CROSS-ASSET HEADWINDS');
assert.ok(mockRibbon.innerHTML.includes('class="macro-regime-badge bearish"'), 'VIX badge should have bearish class');
console.log('  ✓ PASS: Cross-asset headwinds correctly rendered with crimson bearish styling');

// TEST 4: Null / Empty Macro Context Handling
console.log('\n--- TEST 4: Graceful Degradation on Empty / Offline ---');
view.renderMacroRibbon(null);
assert.strictEqual(mockRibbon.style.display, 'none', 'Ribbon should hide on null context');
assert.strictEqual(mockRibbon.innerHTML, '', 'Ribbon should clear HTML on null context');
console.log('  ✓ PASS: Ribbon cleanly hides when macro context is unavailable');

console.log('\n==================================================================');
console.log('  ALL SPX MACRO CORRELATION RIBBON TESTS PASSED (100% GREEN)');
console.log('==================================================================');
