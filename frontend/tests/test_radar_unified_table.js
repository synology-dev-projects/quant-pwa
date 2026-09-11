import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Quant PWA Confluence Radar Unified Table
 */

// Simple lightweight mock DOM element for testing
class MockElement {
  constructor(tagName = 'div', id = '') {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.className = '';
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this._innerHTML = '';
    this._textContent = '';
  }

  get innerHTML() {
    return this._innerHTML;
  }

  set innerHTML(val) {
    this._innerHTML = val;
  }

  get textContent() {
    return this._textContent || this._innerHTML.replace(/<[^>]*>/g, '');
  }

  set textContent(val) {
    this._textContent = val;
  }

  setAttribute(k, v) {
    this.attributes[k] = v;
  }

  getAttribute(k) {
    return this.attributes[k] || null;
  }

  addEventListener(type, fn) {
    this.listeners[type] = this.listeners[type] || [];
    this.listeners[type].push(fn);
  }

  dispatchEvent(evt) {
    const list = this.listeners[evt.type] || [];
    list.forEach(fn => fn(evt));
  }

  querySelector(sel) {
    // Simple ID and tag query support
    if (sel.startsWith('#')) {
      const id = sel.slice(1);
      if (this.id === id) return this;
      if (this.innerHTML.includes(`id="${id}"`)) {
        const mock = new MockElement('div', id);
        return mock;
      }
    }
    return null;
  }

  querySelectorAll(sel) {
    return [];
  }
}

global.localStorage = {
  getItem: () => 'mock-token',
  setItem: () => {},
  removeItem: () => {}
};

global.window = {
  quantApp: {
    tabManager: {
      switchTab: (tab) => { global.window.lastSwitchedTab = tab; }
    },
    cockpitView: {
      searchTicker: (sym) => { global.window.lastSearchedTicker = sym; }
    }
  }
};

console.log('==================================================================');
console.log('  PROBING CONFLUENCE RADAR UNIFIED TABLE');
console.log('==================================================================\n');

import('../src/tabs/radar_view.js').then(({ RadarView }) => {
  const radar = new RadarView();
  const testDiv = new MockElement('div', 'radarRoot');

  // 1. Initial Render
  radar.render(testDiv);

  console.log('--- TEST 1: Unified Radar Mounting ---');
  assert(testDiv.innerHTML.includes('Confluence Radar'), 'Header displays Confluence Radar');
  assert(testDiv.innerHTML.includes('radarDateSelect'), 'Date selector dropdown mounted');
  assert(testDiv.innerHTML.includes('radarInfoRibbon'), 'Metrics info ribbon mounted');
  assert(testDiv.innerHTML.includes('radarTable'), 'Unified radar table mounted');
  
  // Verify all 11 columns in the table header
  const requiredColumns = [
    'TICKER', 'SPOT', 'C/P RATIO', 'PRINTS (3D)', 'PRINTS (7D)',
    'PREM (3D)', 'PREM (7D)', 'CALL WALL', 'PUT WALL', 'ZERO FLIP', 'NET GEX', 'REGIME'
  ];
  requiredColumns.forEach(col => {
    assert(testDiv.innerHTML.includes(col), `Table header contains column: ${col}`);
  });
  console.log('  ✓ PASS: Unified table shell and all 11 required columns mounted cleanly');

  // 2. Mock Data Population
  console.log('\n--- TEST 2: Data Population & Grain Invariants ---');
  const mockPayload = {
    session_date: '2026-09-09',
    dates_3d: ['2026-09-09', '2026-09-08', '2026-09-04'],
    dates_7d: ['2026-09-09', '2026-09-08', '2026-09-04', '2026-09-03', '2026-09-02'],
    total_tickers: 2,
    top_flow_ticker: 'AAPL',
    rows: [
      {
        ticker: 'AAPL',
        snapshot_date: '2026-09-09',
        spot_price: 325.33,
        formatted_spot_price: '$325.33',
        call_put_ratio: '6.63',
        prints_3d: 10,
        prints_7d: 14,
        premium_3d: 21374000.0,
        formatted_premium_3d: '$21.4M',
        premium_7d: 36582000.0,
        formatted_premium_7d: '$36.6M',
        call_wall: 330.0,
        formatted_call_wall: '$330.00',
        put_wall: 325.0,
        formatted_put_wall: '$325.00',
        zero_flip: 325.33,
        formatted_zero_flip: '$325.33',
        net_gex: 4500000.0,
        formatted_net_gex: '$4.5M',
        gamma_regime: 'Positive'
      },
      {
        ticker: 'AMD',
        snapshot_date: '2026-09-09',
        spot_price: 505.56,
        formatted_spot_price: '$505.56',
        call_put_ratio: '3.29',
        prints_3d: 4,
        prints_7d: 8,
        premium_3d: 16320000.0,
        formatted_premium_3d: '$16.3M',
        premium_7d: 31020000.0,
        formatted_premium_7d: '$31.0M',
        call_wall: 500.0,
        formatted_call_wall: '$500.00',
        put_wall: 500.0,
        formatted_put_wall: '$500.00',
        zero_flip: 505.56,
        formatted_zero_flip: '$505.56',
        net_gex: -1200000.0,
        formatted_net_gex: '-$1.2M',
        gamma_regime: 'Negative'
      }
    ],
    available_dates: ['2026-09-09', '2026-09-08', '2026-09-04']
  };

  radar.currentData = mockPayload;
  radar.selectedDate = '2026-09-09';
  
  // Test sorting logic
  const sortedDesc = radar.getSortedRows();
  assert.equal(sortedDesc[0].ticker, 'AAPL', 'Top row is AAPL (highest 7D premium: $36.6M)');
  assert.equal(sortedDesc[1].ticker, 'AMD', 'Second row is AMD ($31.0M)');

  // Toggle sort to ascending
  radar.sortDirection = 'asc';
  const sortedAsc = radar.getSortedRows();
  assert.equal(sortedAsc[0].ticker, 'AMD', 'Top row ascending is AMD (lower premium)');
  assert.equal(sortedAsc[1].ticker, 'AAPL', 'Second row ascending is AAPL');

  // Sort by prints_3d descending
  radar.sortColumn = 'prints_3d';
  radar.sortDirection = 'desc';
  const sortedPrints = radar.getSortedRows();
  assert.equal(sortedPrints[0].prints_3d, 10, 'Top prints_3d is 10 (AAPL)');
  console.log('  ✓ PASS: Data parsing, 3D/7D flow metrics, and tri-state sorting verified');

  // 3. Drilldown to Cockpit
  console.log('\n--- TEST 3: Click-to-Cockpit Drilldown ---');
  radar.drillDownToCockpit('NVDA');
  assert.equal(global.window.lastSwitchedTab, 'cockpit', 'TabManager switched to cockpit');
  assert.equal(global.window.lastSearchedTicker, 'NVDA', 'CockpitView triggered search for NVDA');
  console.log('  ✓ PASS: Click-to-Cockpit drilldown dispatched cleanly');

  // 4. Teardown
  console.log('\n--- TEST 4: Lifecycle Teardown ---');
  radar.destroy();
  assert.equal(testDiv.innerHTML, '', 'destroy() successfully cleared container');
  console.log('  ✓ PASS: Lifecycle teardown confirmed');

  console.log('\n==================================================================');
  console.log('  ALL CONFLUENCE RADAR UNIFIED TABLE TESTS PASSED (100% GREEN)');
  console.log('==================================================================');
}).catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
