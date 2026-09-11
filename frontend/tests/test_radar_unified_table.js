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
  
  // Verify all 10 columns in the table header
  const requiredColumns = [
    'TICKER', 'SPOT', 'C/P RATIO', 'PRINTS (3D)', 'PRINTS (7D)',
    'PREM (3D)', 'PREM (7D)', 'CALL WALL', 'PUT WALL', 'ZERO FLIP'
  ];
  requiredColumns.forEach(col => {
    assert(testDiv.innerHTML.includes(col), `Table header contains column: ${col}`);
  });
  assert(!testDiv.innerHTML.includes('>NET GEX<'), 'NET GEX column is removed');
  assert(!testDiv.innerHTML.includes('>REGIME<'), 'REGIME column is removed');
  console.log('  ✓ PASS: Unified table shell and all 10 required columns mounted cleanly (NET GEX and REGIME verified removed)');

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
        formatted_zero_flip: '$325.33'
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
        formatted_zero_flip: '$505.56'
      }
    ],
    available_dates: ['2026-09-09', '2026-09-08', '2026-09-04']
  };

  radar.currentData = mockPayload;
  radar.selectedDate = '2026-09-09';
  
  // Test sorting logic
  radar.sortColumn = 'premium_7d';
  radar.sortDirection = 'desc';
  const sortedDesc = radar.getSortedRows();
  assert.equal(sortedDesc[0].ticker, 'AAPL', 'Top row is AAPL (highest 7D premium: $36.6M)');
  assert.equal(sortedDesc[1].ticker, 'AMD', 'Second row is AMD ($31.0M)');

  // Toggle sort to ascending on press
  radar.handleSort('premium_7d');
  assert.equal(radar.sortDirection, 'asc', 'Pressing sorted column toggles to asc');
  const sortedAsc = radar.getSortedRows();
  assert.equal(sortedAsc[0].ticker, 'AMD', 'Top row ascending is AMD (lower premium)');
  assert.equal(sortedAsc[1].ticker, 'AAPL', 'Second row ascending is AAPL');

  // Toggle sort back to descending on next press
  radar.handleSort('premium_7d');
  assert.equal(radar.sortDirection, 'desc', 'Pressing sorted column again toggles back to desc');
  const sortedDescAgain = radar.getSortedRows();
  assert.equal(sortedDescAgain[0].ticker, 'AAPL', 'Top row descending is AAPL');

  // Sort by prints_3d (defaults to desc)
  radar.handleSort('prints_3d');
  assert.equal(radar.sortColumn, 'prints_3d');
  assert.equal(radar.sortDirection, 'desc', 'New numeric column defaults to desc');
  const sortedPrints = radar.getSortedRows();
  assert.equal(sortedPrints[0].prints_3d, 10, 'Top prints_3d is 10 (AAPL)');

  // Toggle prints_3d to asc
  radar.handleSort('prints_3d');
  assert.equal(radar.sortDirection, 'asc', 'Pressing prints_3d toggles to asc');
  const sortedPrintsAsc = radar.getSortedRows();
  assert.equal(sortedPrintsAsc[0].prints_3d, 4, 'Top prints_3d ascending is 4 (AMD)');

  console.log('  ✓ PASS: Direct ASC/DESC header press toggling and metric sorting verified');

  // 3. Drilldown to Cockpit
  console.log('\n--- TEST 3: Click-to-Cockpit Drilldown ---');
  radar.drillDownToCockpit('NVDA');
  assert.equal(global.window.lastSwitchedTab, 'cockpit', 'TabManager switched to cockpit');
  assert.equal(global.window.lastSearchedTicker, 'NVDA', 'CockpitView triggered search for NVDA');
  console.log('  ✓ PASS: Click-to-Cockpit drilldown dispatched cleanly');

  // 4. C/P Ratio Highlighting Rules (> 3 green, 1-3 yellow, < 1 red)
  console.log('\n--- TEST 4: C/P Ratio Color Highlighting ---');
  assert(radar.getRatioClass('3.5').includes('ratio-high'), 'Ratio > 3 gets ratio-high');
  assert(radar.getRatioClass('3.5').includes('ratio-green'), 'Ratio > 3 gets ratio-green');
  assert(radar.getRatioClass('6.63').includes('ratio-high'), 'Ratio 6.63 gets ratio-high');
  
  assert(radar.getRatioClass('0.93').includes('ratio-low'), 'Ratio < 1 gets ratio-low');
  assert(radar.getRatioClass('0.93').includes('ratio-red'), 'Ratio < 1 gets ratio-red');
  assert(radar.getRatioClass('0.45').includes('ratio-low'), 'Ratio 0.45 gets ratio-low');
  
  assert(radar.getRatioClass('1.0').includes('ratio-mid'), 'Ratio 1.0 gets ratio-mid');
  assert(radar.getRatioClass('1.88').includes('ratio-mid'), 'Ratio 1.88 gets ratio-mid');
  assert(radar.getRatioClass('1.88').includes('ratio-yellow'), 'Ratio 1.88 gets ratio-yellow');
  assert(radar.getRatioClass('3.0').includes('ratio-mid'), 'Ratio 3.0 gets ratio-mid');

  assert.equal(radar.getRatioClass('N/A'), '', 'N/A gets empty class');
  assert.equal(radar.getRatioClass(null), '', 'Null gets empty class');
  assert.equal(radar.getRatioClass(''), '', 'Empty gets empty class');
  console.log('  ✓ PASS: C/P ratio color thresholds verified (> 3 green, 1-3 yellow, < 1 red)');

  // 5. Teardown
  console.log('\n--- TEST 5: Lifecycle Teardown ---');
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
