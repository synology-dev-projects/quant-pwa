import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Quant PWA SPX Levels View (PWA-01)
 */

console.log('==================================================================');
console.log('  PROBING SPX QUANT LEVELS VIEW COMPONENT');
console.log('==================================================================\n');

// Mock browser globals
global.window = {
  location: { origin: 'http://127.0.0.1:8000', hostname: '127.0.0.1', port: '8000' },
  localStorage: {
    getItem: (key) => {
      if (key === 'quant_session_token') return 'mock-token';
      return null;
    },
    setItem: () => {},
    removeItem: () => {}
  }
};
global.localStorage = global.window.localStorage;
global.document = {
  createElement: (tag) => ({
    tagName: tag.toUpperCase(),
    value: '',
    textContent: '',
    selected: false
  })
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
  return {
    ok: true,
    status: 200,
    json: async () => ({})
  };
};

import('../src/tabs/levels_view.js').then(async ({ LevelsView }) => {
  const levelsView = new LevelsView();

  console.log('--- TEST 1: SPX Ticker Lock & Shell Mounting ---');
  assert.equal(levelsView.ticker, 'SPX', 'LevelsView is strictly locked to SPX');

  const container = {
    innerHTML: '',
    querySelector: (sel) => {
      if (sel === '#levelsDateSelect') {
        return {
          innerHTML: '',
          children: [],
          appendChild: (c) => {},
          addEventListener: () => {}
        };
      }
      if (sel === '#levelsRefreshBtn') {
        return {
          addEventListener: () => {}
        };
      }
      if (sel === '#levelsContentMount') {
        return {
          innerHTML: '',
          querySelector: () => null
        };
      }
      return null;
    }
  };

  levelsView.render(container);

  assert(container.innerHTML.includes('SPX 500'), 'Header renders SPX 500 badge');
  assert(container.innerHTML.includes('Quant Levels Terminal'), 'Header title contains Quant Levels Terminal');
  assert(container.innerHTML.includes('S&P 500 Daily Pivot'), 'Subtitle mentions S&P 500');
  assert(container.innerHTML.includes('levelsDateSelect'), 'Date selector dropdown mounted');
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

  // Verify Spot Marker position between 5650.00 (SELL) and 5580.00 (PIVOT)
  const idx5650 = ladderHtml.indexOf('5650.00');
  const idxSpot = ladderHtml.indexOf('ladderSpotMarker');
  const idx5580 = ladderHtml.indexOf('5580.00');
  assert(idx5650 < idxSpot, 'Resistance 5650 comes before spot marker in descending ladder');
  assert(idxSpot < idx5580, 'Spot marker comes before support/pivot 5580 in descending ladder');

  // Verify level tags and classes
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

  console.log('\n==================================================================');
  console.log('  ALL SPX QUANT LEVELS VIEW TESTS PASSED (100% GREEN)');
  console.log('==================================================================');
  process.exit(0);
}).catch((err) => {
  console.error('Test failed:', err);
  process.exit(1);
});
