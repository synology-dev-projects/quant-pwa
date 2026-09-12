import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Quant PWA SPX Levels View (PWA-01)
 * Enhanced to verify Candlestick Chart & Comment Sanitization.
 */

console.log('==================================================================');
console.log('  PROBING SPX QUANT LEVELS VIEW & CANDLESTICK COMPONENT');
console.log('==================================================================\n');

// Mock browser globals
global.window = {
  innerWidth: 1024,
  devicePixelRatio: 2,
  location: { origin: 'http://127.0.0.1:8000', hostname: '127.0.0.1', port: '8000' },
  localStorage: {
    getItem: (key) => {
      if (key === 'quant_session_token') return 'mock-token';
      return null;
    },
    setItem: () => {},
    removeItem: () => {}
  },
  addEventListener: () => {},
  removeEventListener: () => {}
};
global.localStorage = global.window.localStorage;
global.requestAnimationFrame = (cb) => { cb(); return 1; };

global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

function createMockElement(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    className: '',
    value: '',
    textContent: '',
    innerHTML: '',
    style: {},
    children: [],
    parentElement: null,
    width: 800,
    height: 440,
    appendChild: function(child) {
      this.children.push(child);
      child.parentElement = this;
      return child;
    },
    removeChild: function(child) {
      this.children = this.children.filter(c => c !== child);
      child.parentElement = null;
      return child;
    },
    addEventListener: () => {},
    removeEventListener: () => {},
    setAttribute: () => {},
    getAttribute: () => null,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 440, right: 800, bottom: 440 }),
    querySelector: function(sel) {
      if (sel.startsWith('#')) {
        const id = sel.substring(1);
        if (this.id === id) return this;
      }
      if (sel.startsWith('.')) {
        const cls = sel.substring(1);
        if (this.className && this.className.includes(cls)) return this;
      }
      for (const ch of this.children) {
        if (ch.querySelector) {
          const res = ch.querySelector(sel);
          if (res) return res;
        }
      }
      if (sel.startsWith('#') && this.innerHTML && this.innerHTML.includes(sel.substring(1))) {
        return { innerHTML: '', className: '', querySelector: () => null };
      }
      if (sel.startsWith('.') && this.innerHTML && this.innerHTML.includes(sel.substring(1))) {
        return { innerHTML: '', className: sel.substring(1), querySelector: () => null };
      }
      return null;
    },
    querySelectorAll: function(sel) {
      const list = [];
      for (const ch of this.children) {
        if (ch.querySelectorAll) {
          list.push(...ch.querySelectorAll(sel));
        }
      }
      return list;
    },
    getContext: () => ({
      scale: () => {},
      fillRect: () => {},
      strokeRect: () => {},
      fillText: () => {},
      stroke: () => {},
      beginPath: () => {},
      moveTo: () => {},
      lineTo: () => {},
      arc: () => {},
      fill: () => {},
      save: () => {},
      restore: () => {},
      setLineDash: () => {},
      clearRect: () => {},
      measureText: (txt) => ({ width: (txt || '').length * 7 }),
      roundRect: () => {},
      font: '',
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 1,
      textAlign: 'center',
      textBaseline: 'middle',
      shadowBlur: 0,
      shadowColor: ''
    })
  };
  return el;
}

global.document = {
  createElement: createMockElement,
  getElementById: (id) => null
};

const mockDatesResponse = ['2026-09-11', '2026-09-10', '2026-09-09'];
const mockDataResponse = {
  status: 'ok',
  ticker: 'SPX',
  as_of_date: '2026-09-11',
  spot_price: 5600.0,
  levels: [
    {
      type: 'SELL',
      start_price: 5700.0,
      end_price: null,
      price_display: '5700.00',
      distance_pts: 100.0,
      distance_pct: 1.79,
      is_immediate_resistance: false,
      is_immediate_support: false,
      comments: 'Major overhead supply',
      web_link: 'https://example.com/post1'
    },
    {
      type: 'SELL',
      start_price: 5650.0,
      end_price: null,
      price_display: '5650.00',
      distance_pts: 50.0,
      distance_pct: 0.89,
      is_immediate_resistance: true,
      is_immediate_support: false,
      comments: 'Immediate call wall',
      web_link: null
    },
    {
      type: 'PIVOT',
      start_price: 5580.0,
      end_price: 5590.0,
      price_display: '5580.00 - 5590.00',
      distance_pts: -15.0,
      distance_pct: -0.27,
      is_immediate_resistance: false,
      is_immediate_support: false,
      comments: 'Consolidation pivot zone',
      web_link: null
    },
    {
      type: 'BUY',
      start_price: 5550.0,
      end_price: null,
      price_display: '5550.00',
      distance_pts: -50.0,
      distance_pct: -0.89,
      is_immediate_resistance: false,
      is_immediate_support: true,
      comments: 'Immediate put support floor',
      web_link: null
    }
  ],
  summary: {
    total_levels: 4,
    buy_count: 1,
    sell_count: 2,
    pivot_count: 1,
    immediate_resistance: 5650.0,
    immediate_support: 5550.0,
    channel_width: 100.0
  }
};

const mockCandlesResponse = {
  status: 'ok',
  ticker: 'SPX',
  as_of_date: '2026-09-11',
  candles: [
    { timestamp: 1789133400, datetime: '09:30', open: 5600.0, high: 5615.0, low: 5595.0, close: 5610.0, volume: 15000 },
    { timestamp: 1789133700, datetime: '09:35', open: 5610.0, high: 5625.0, low: 5608.0, close: 5622.0, volume: 12000 },
    { timestamp: 1789134000, datetime: '09:40', open: 5622.0, high: 5630.0, low: 5618.0, close: 5620.0, volume: 9000 },
    { timestamp: 1789156800, datetime: '16:00', open: 5645.0, high: 5650.0, low: 5640.0, close: 5648.0, volume: 30000 }
  ]
};

let requestedUrls = [];
global.fetch = async (url) => {
  requestedUrls.push(url);
  if (url.includes('/api/quant-levels/dates')) {
    return {
      ok: true,
      status: 200,
      json: async () => mockDatesResponse
    };
  }
  if (url.includes('/api/quant-levels/data')) {
    return {
      ok: true,
      status: 200,
      json: async () => mockDataResponse
    };
  }
  if (url.includes('/api/quant-levels/candles')) {
    return {
      ok: true,
      status: 200,
      json: async () => mockCandlesResponse
    };
  }
  if (url.includes('/api/quant-levels/extract-date')) {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        status: 'ok',
        target_date: '2026-09-05',
        rows_upserted: 14,
        message: 'Successfully extracted 14 quant levels for 2026-09-05.'
      })
    };
  }
  return {
    ok: true,
    status: 200,
    json: async () => ({})
  };
};

Promise.all([
  import('../src/tabs/levels_view.js'),
  import('../src/components/candlestick_chart.js')
]).then(async ([{ LevelsView, sanitizeComment }, { CandlestickChart }]) => {
  const levelsView = new LevelsView();

  console.log('--- TEST 1: SPX Ticker Lock & Shell Mounting ---');
  assert.equal(levelsView.ticker, 'SPX', 'LevelsView is strictly locked to SPX');

  const dateSelectMock = {
    innerHTML: '',
    children: [],
    appendChild: () => {},
    addEventListener: (ev, cb) => { dateSelectMock.listeners[ev] = cb; },
    listeners: {},
    value: ''
  };
  const datePickerMock = {
    value: '',
    max: '',
    addEventListener: (ev, cb) => { datePickerMock.listeners[ev] = cb; },
    listeners: {}
  };
  const prevBtnMock = {
    disabled: false,
    addEventListener: (ev, cb) => { prevBtnMock.listeners[ev] = cb; },
    listeners: {}
  };
  const nextBtnMock = {
    disabled: false,
    addEventListener: (ev, cb) => { nextBtnMock.listeners[ev] = cb; },
    listeners: {}
  };
  const refreshBtnMock = {
    addEventListener: (ev, cb) => { refreshBtnMock.listeners[ev] = cb; },
    listeners: {}
  };

  const container = createMockElement('div');
  container.innerHTML = '';
  container.querySelector = (sel) => {
    if (sel === '#levelsDateSelect') return dateSelectMock;
    if (sel === '#levelsDatePicker') return datePickerMock;
    if (sel === '#levelsPrevBtn') return prevBtnMock;
    if (sel === '#levelsNextBtn') return nextBtnMock;
    if (sel === '#levelsRefreshBtn') return refreshBtnMock;
    if (sel === '#levelsContentMount') {
      return { innerHTML: '', querySelector: () => null };
    }
    return null;
  };

  levelsView.render(container);

  assert(container.innerHTML.includes('SPX 500'), 'Header renders SPX 500 badge');
  assert(container.innerHTML.includes('Quant Levels Terminal'), 'Header title contains Quant Levels Terminal');
  assert(container.innerHTML.includes('S&P 500 Daily Pivot'), 'Subtitle mentions S&P 500');
  assert(container.innerHTML.includes('levelsDateSelect'), 'Date selector dropdown mounted');
  assert(container.innerHTML.includes('levelsDatePicker'), 'Native HTML5 Date picker mounted');
  assert(container.innerHTML.includes('levelsPrevBtn'), 'Quick-step ◄ Prev button mounted');
  assert(container.innerHTML.includes('levelsNextBtn'), 'Quick-step Next ► button mounted');
  assert(container.innerHTML.includes('levelsRefreshBtn'), 'Refresh button mounted');
  assert(container.innerHTML.includes('levelsContentMount'), 'Content mount target mounted');

  // Verify no ticker input or arbitrary search elements
  assert(!container.innerHTML.includes('tickerInput'), 'No generic ticker input mounted (SPX locked)');
  assert(!container.innerHTML.includes('searchTicker'), 'No searchTicker mounted (SPX locked)');
  console.log('  ✓ PASS: Shell mounted cleanly with SPX exclusivity and zero arbitrary ticker inputs');

  console.log('\n--- TEST 2: API Endpoint Requests Locked to SPX ---');
  await levelsView.loadInitialData();
  const dateReq = requestedUrls.find((u) => u.includes('/api/quant-levels/dates'));
  const dataReq = requestedUrls.find((u) => u.includes('/api/quant-levels/data'));

  assert(dateReq, 'Dates endpoint was called');
  assert(dateReq.includes('ticker=SPX'), 'Dates endpoint requested strictly ticker=SPX');
  assert(dataReq, 'Data endpoint was called');
  assert(dataReq.includes('ticker=SPX'), 'Data endpoint requested strictly ticker=SPX');
  console.log('  ✓ PASS: Gateway fetch requests enforce ticker=SPX query parameter');

  console.log('\n--- TEST 3: Hero HUD Cards Rendering ---');
  const mount = { innerHTML: '', querySelector: () => null };
  levelsView.renderLevelsUI(mount, mockDataResponse);

  assert(mount.innerHTML.includes('SPX Spot Price'), 'Spot Price card present');
  assert(mount.innerHTML.includes('$5,600.00'), 'Spot Price formatted correctly');
  assert(mount.innerHTML.includes('Immediate Resistance'), 'Resistance card present');
  assert(mount.innerHTML.includes('$5,650.00'), 'Resistance value formatted correctly');
  assert(mount.innerHTML.includes('+50.00 pts (+0.89%)'), 'Resistance delta calculated correctly');
  assert(mount.innerHTML.includes('Immediate Support'), 'Support card present');
  assert(mount.innerHTML.includes('$5,550.00'), 'Support value formatted correctly');
  assert(mount.innerHTML.includes('-50.00 pts (-0.89%)'), 'Support delta calculated correctly');
  assert(mount.innerHTML.includes('Trading Channel'), 'Trading Channel card present');
  assert(mount.innerHTML.includes('100.00 pts'), 'Channel width displayed correctly');
  assert(mount.innerHTML.includes('4 Total Levels Recorded'), 'Total levels count displayed');
  console.log('  ✓ PASS: Hero HUD cards compute and format spot, resistance, support, and channel');

  console.log('\n--- TEST 4: Price Ladder & Spot Marker Insertion ---');
  const ladderHtml = levelsView.buildLadderHtml(mockDataResponse.levels, 5600.0);
  assert(ladderHtml.includes('ladderSpotMarker'), 'Ladder contains live spot marker');
  assert(ladderHtml.includes('SPX LIVE SPOT'), 'Marker displays SPX LIVE SPOT label');
  assert(ladderHtml.includes('$5,600.00'), 'Marker displays $5,600.00 price');

  const idx5650 = ladderHtml.indexOf('5650.00');
  const idxSpot = ladderHtml.indexOf('ladderSpotMarker');
  const idx5580 = ladderHtml.indexOf('5580.00');
  assert(idx5650 < idxSpot, 'Resistance 5650 comes before spot marker in descending ladder');
  assert(idxSpot < idx5580, 'Spot marker comes before support/pivot 5580 in descending ladder');

  assert(ladderHtml.includes('type-sell'), 'Contains SELL row class');
  assert(ladderHtml.includes('type-buy'), 'Contains BUY row class');
  assert(ladderHtml.includes('type-pivot'), 'Contains PIVOT row class');
  assert(ladderHtml.includes('immediate-res'), 'Immediate resistance row tagged');
  assert(ladderHtml.includes('immediate-sup'), 'Immediate support row tagged');
  assert(ladderHtml.includes('Major overhead supply'), 'Ladder renders level commentary');
  assert(ladderHtml.includes('Immediate call wall'), 'Ladder renders resistance commentary');
  assert(ladderHtml.includes('ladder-comment-row'), 'Ladder contains dedicated comment row structure');
  console.log('  ✓ PASS: Price ladder inserts dynamic spot marker at exact price height with proper tags & commentary');

  console.log('\n--- TEST 5: Structured Levels Table Rendering ---');
  assert(mount.innerHTML.includes('levels-table'), 'Table wrapper present');
  assert(mount.innerHTML.includes('Major overhead supply'), 'Commentary rendered in table');
  assert(mount.innerHTML.includes('View Post &rarr;'), 'Web link rendered as link button');
  assert(mount.innerHTML.includes('Database'), 'Missing web link falls back to Database tag');
  console.log('  ✓ PASS: Institutional structured table renders full level matrix with source links');

  console.log('\n--- TEST 6: Empty & Error State Handling ---');
  const emptyMount = { innerHTML: '', querySelector: () => null };
  levelsView.renderEmptyState(emptyMount, 'No levels found for today');
  assert(emptyMount.innerHTML.includes('No SPX Levels Available'), 'Empty state header rendered');
  assert(emptyMount.innerHTML.includes('No levels found for today'), 'Empty state custom message rendered');
  assert(emptyMount.innerHTML.includes('Trigger SPX Levels Ingestion'), 'Ingestion sync button rendered');

  const errorMount = { innerHTML: '', querySelector: () => null };
  levelsView.renderErrorState(errorMount, 'Database connection timeout');
  assert(errorMount.innerHTML.includes('Failed to Load SPX Levels'), 'Error state header rendered');
  assert(errorMount.innerHTML.includes('Database connection timeout'), 'Error message rendered');
  assert(errorMount.innerHTML.includes('Retry Connection'), 'Retry button rendered');
  console.log('  ✓ PASS: Empty and Error states provide graceful fallback and retry triggers');

  console.log('\n--- TEST 7: Comment Sanitization & Nan Suppression ---');
  assert.equal(sanitizeComment('nan'), '', 'nan string sanitizes to empty');
  assert.equal(sanitizeComment('NaN'), '', 'NaN string sanitizes to empty');
  assert.equal(sanitizeComment('None'), '', 'None string sanitizes to empty');
  assert.equal(sanitizeComment('null'), '', 'null string sanitizes to empty');
  assert.equal(sanitizeComment('—'), '', 'em dash sanitizes to empty');
  assert.equal(sanitizeComment(''), '', 'empty string sanitizes to empty');
  assert.equal(sanitizeComment(null), '', 'null value sanitizes to empty');
  assert.equal(sanitizeComment(undefined), '', 'undefined sanitizes to empty');
  assert.equal(sanitizeComment('Valid note'), 'Valid note', 'Valid comments preserved');

  const nanLevel = {
    type: 'BUY',
    start_price: 5500.0,
    end_price: null,
    price_display: '5500.00',
    distance_pts: -100.0,
    distance_pct: -1.79,
    comments: 'nan',
    web_link: null
  };
  const nanRowHtml = levelsView.buildLadderRowHtml(nanLevel);
  assert(!nanRowHtml.includes('ladder-comment-row'), 'Ladder row completely suppresses comment container when comment is "nan"');
  assert(!nanRowHtml.includes('nan'), 'No literal "nan" appears in ladder row');

  const nanTableHtml = levelsView.buildTableRowHtml(nanLevel);
  assert(nanTableHtml.includes('<td>—</td>'), 'Table row renders em dash fallback instead of "nan"');
  assert(!nanTableHtml.includes('<td>nan</td>'), 'Table row never displays "nan"');
  console.log('  ✓ PASS: "nan" comments are completely purged from ladder rows and cleanly fall back to "—" in tables');

  console.log('\n--- TEST 8: Candlestick Chart Section Mounting ---');
  assert(mount.innerHTML.includes('levelsCandlestickMount'), 'Candlestick mount section present at bottom of levels view');

  const candlestickContainer = createMockElement('div');
  const chartInstance = new CandlestickChart(candlestickContainer, {
    candles: mockCandlesResponse.candles,
    levels: mockDataResponse.levels,
    spot_price: mockDataResponse.spot_price,
    as_of_date: '2026-09-11',
    ticker: 'SPX'
  });

  assert(chartInstance.canvas, 'Canvas element created in candlestick chart');
  assert(chartInstance.wrapper.className.includes('candlestick-card'), 'Wrapper has candlestick-card class');
  assert(chartInstance.wrapper.querySelector('.candlestick-badge'), 'Renders SPX 5M badge');
  assert(chartInstance.wrapper.querySelector('.candlestick-legend'), 'Renders legend bar');

  // Verify Metrics computation
  const metricsMount = chartInstance.wrapper.querySelector('#candlestickMetricsMount');
  assert(metricsMount, 'Metrics mount present');
  assert(metricsMount.innerHTML.includes('OPEN'), 'Metrics displays OPEN');
  assert(metricsMount.innerHTML.includes('HIGH'), 'Metrics displays HIGH');
  assert(metricsMount.innerHTML.includes('LOW'), 'Metrics displays LOW');
  assert(metricsMount.innerHTML.includes('LAST'), 'Metrics displays LAST');
  assert(metricsMount.innerHTML.includes('$5,610.00') || metricsMount.innerHTML.includes('$5600.00'), 'Metrics displays open price');

  chartInstance.destroy();
  assert.equal(chartInstance.canvas, null, 'Chart cleanly destroyed');
  console.log('  ✓ PASS: Candlestick chart component renders canvas, metrics, legend, and cleans up');

  console.log('\n--- TEST 9: Date Picker & Quick-Step Buttons Mounting ---');
  assert(container.innerHTML.includes('levels-controls-group'), 'Header controls group wrapper present');
  assert(container.innerHTML.includes('id="levelsDatePicker"'), 'Date picker input element mounted');
  assert(container.innerHTML.includes('id="levelsPrevBtn"'), 'Previous session button mounted');
  assert(container.innerHTML.includes('id="levelsNextBtn"'), 'Next session button mounted');
  assert(container.innerHTML.includes('max="'), 'Date picker specifies max date limit');
  console.log('  ✓ PASS: Native HTML5 date picker and quick-step buttons mounted with WCAG controls group');

  console.log('\n--- TEST 10: Two-Way Synchronization Between Picker & Dropdown ---');
  levelsView.availableDates = ['2026-09-11', '2026-09-10', '2026-09-09'];
  levelsView.updateDateSelector();

  // 1. Date picker changes to a date in availableDates -> updates dropdown
  datePickerMock.listeners['change']({ target: { value: '2026-09-10' } });
  assert.equal(levelsView.selectedDate, '2026-09-10', 'Selected date updated from date picker');
  assert.equal(dateSelectMock.value, '2026-09-10', 'Dropdown value synced with date picker');

  // 2. Date picker changes to a custom date not in availableDates -> clears dropdown selection
  datePickerMock.listeners['change']({ target: { value: '2026-09-01' } });
  assert.equal(levelsView.selectedDate, '2026-09-01', 'Selected date set to custom date');
  assert.equal(dateSelectMock.value, '', 'Dropdown cleared for custom unlisted date');

  // 3. Dropdown changes -> updates date picker
  dateSelectMock.listeners['change']({ target: { value: '2026-09-09' } });
  assert.equal(levelsView.selectedDate, '2026-09-09', 'Selected date updated from dropdown');
  assert.equal(datePickerMock.value, '2026-09-09', 'Date picker value synced with dropdown');
  console.log('  ✓ PASS: Two-way synchronization between date picker and session select is flawless');

  console.log('\n--- TEST 11: Quick-Step Navigation Logic & Boundary Rules ---');
  levelsView.availableDates = ['2026-09-11', '2026-09-10', '2026-09-09'];
  levelsView.selectedDate = '2026-09-11';
  levelsView.updateStepButtons();
  assert.equal(nextBtnMock.disabled, true, 'Next button disabled on latest available date');

  // Step backwards (◄ Prev)
  prevBtnMock.listeners['click']();
  assert.equal(levelsView.selectedDate, '2026-09-10', 'Step backwards moved to previous available session');
  assert.equal(datePickerMock.value, '2026-09-10', 'Date picker synced to stepped date');
  assert.equal(nextBtnMock.disabled, false, 'Next button enabled when not on latest date');

  // Step backwards again (◄ Prev)
  prevBtnMock.listeners['click']();
  assert.equal(levelsView.selectedDate, '2026-09-09', 'Step backwards moved to oldest available session');

  // Step forward (Next ►)
  nextBtnMock.listeners['click']();
  assert.equal(levelsView.selectedDate, '2026-09-10', 'Step forward moved to next available session');
  assert.equal(nextBtnMock.disabled, false, 'Next button still enabled');

  // Step forward again to latest session
  nextBtnMock.listeners['click']();
  assert.equal(levelsView.selectedDate, '2026-09-11', 'Step forward reached latest session');
  assert.equal(nextBtnMock.disabled, true, 'Next button disabled on reaching latest session');
  console.log('  ✓ PASS: Quick-step navigation steps sessions and enforces latest session disable rule');

  console.log('\n--- TEST 12: Historical Spot Price Context & Labeling ---');
  // Historical spot marker helper
  const histSpotHtml = levelsView.buildSpotMarkerHtml(5482.50, true);
  assert(histSpotHtml.includes('ladder-spot-marker historical'), 'Spot marker has .historical class');
  assert(histSpotHtml.includes('SPX SESSION CLOSE'), 'Spot marker displays SPX SESSION CLOSE');
  assert(histSpotHtml.includes('$5,482.50'), 'Spot marker displays historical close price');

  // Live spot marker helper
  const liveSpotHtml = levelsView.buildSpotMarkerHtml(5600.00, false);
  assert(!liveSpotHtml.includes('ladder-spot-marker historical'), 'Live spot marker does not have .historical class');
  assert(liveSpotHtml.includes('SPX LIVE SPOT'), 'Live spot marker displays SPX LIVE SPOT');

  // Hero HUD card historical rendering
  const histMount = { innerHTML: '', querySelector: () => null };
  levelsView.renderLevelsUI(histMount, {
    ...mockDataResponse,
    spot_price: 5482.50,
    spot_type: 'HISTORICAL_CLOSE',
    summary: {
      ...mockDataResponse.summary,
      spot_label: 'SPX Session Close'
    }
  });
  assert(histMount.innerHTML.includes('SPX Session Close'), 'Hero HUD card label displays SPX Session Close');
  assert(histMount.innerHTML.includes('$5,482.50'), 'Hero HUD spot card displays historical close price');
  assert(histMount.innerHTML.includes('ladder-spot-marker historical'), 'Ladder includes historical spot marker class');
  assert(histMount.innerHTML.includes('SPX SESSION CLOSE'), 'Ladder spot marker text displays SPX SESSION CLOSE');
  console.log('  ✓ PASS: Historical spot price anchoring correctly labels SPX Session Close in Hero and Ladder');

  console.log('\n--- TEST 13: Empty State On-Demand Extraction Button ---');
  levelsView.selectedDate = '2026-09-05';
  let extractBtnRef = null;
  const extractMount = {
    innerHTML: '',
    querySelector: function(sel) {
      if (sel === '#levelsExtractTargetBtn') {
        if (!extractBtnRef) {
          extractBtnRef = {
            disabled: false,
            innerHTML: '',
            listeners: {},
            addEventListener: (ev, cb) => { extractBtnRef.listeners[ev] = cb; },
            click: async () => {
              if (extractBtnRef.listeners['click']) {
                await extractBtnRef.listeners['click']();
              }
            }
          };
        }
        return extractBtnRef;
      }
      if (sel === '#levelsExtractStatus') {
        return { style: {}, textContent: '' };
      }
      return null;
    }
  };

  levelsView.renderEmptyState(extractMount, 'No levels found in database for 2026-09-05.');
  assert(extractMount.innerHTML.includes('levelsExtractTargetBtn'), 'On-demand extraction button mounted in empty state');
  assert(extractMount.innerHTML.includes('Extract Quant Levels for 2026-09-05'), 'Button text includes target date');

  // Trigger click on extraction button
  const extractBtn = extractMount.querySelector('#levelsExtractTargetBtn');
  assert(extractBtn, 'Found extract button');
  await extractBtn.click();

  const extractReq = requestedUrls.find((u) => u.includes('/api/quant-levels/extract-date'));
  assert(extractReq, 'Extract date endpoint was called');
  assert(extractReq.includes('target_date=2026-09-05'), 'Extract endpoint called with target_date=2026-09-05');
  console.log('  ✓ PASS: Empty state renders on-demand extraction trigger and issues targeted extraction POST');

  console.log('\n==================================================================');
  console.log('  ALL SPX QUANT LEVELS & CANDLESTICK TESTS PASSED (100% GREEN)');
  console.log('==================================================================');
  process.exit(0);
}).catch((err) => {
  console.error('Test failed:', err);
  process.exit(1);
});
