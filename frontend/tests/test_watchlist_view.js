import { strict as assert } from 'assert';

/**
 * In-Situ DOM & Interaction Test for Quant PWA Watchlist View
 */

console.log('==================================================================');
console.log('  PROBING WATCHLIST VIEW COMPONENT');
console.log('==================================================================\n');

// Mock browser globals
global.window = {
  location: { origin: 'http://127.0.0.1:8000', hostname: '127.0.0.1', port: '8000' },
  localStorage: {
    getItem: (key) => {
      if (key === 'quant_gateway_url') return 'http://127.0.0.1:8000';
      if (key === 'quant_session_token') return 'mock-token';
      return null;
    },
    setItem: () => {},
    removeItem: () => {}
  }
};
global.localStorage = global.window.localStorage;
global.fetch = async (url) => ({
  ok: true,
  status: 200,
  json: async () => ([
    {
      id: 'core_watchlist',
      name: 'Core Watchlist',
      tickers: [
        { ticker: 'NVDA', indices: ['S&P 500', 'Nasdaq 100', 'Dow 30'] },
        { ticker: 'SPY', indices: ['Major ETF'] },
        { ticker: 'POWL', indices: ['Russell 2000'] }
      ]
    }
  ])
});

import('../src/tabs/watchlist_view.js').then(({ WatchlistView }) => {
  const watchlistView = new WatchlistView();
  const testDiv = { innerHTML: '', querySelector: () => null };

  console.log('--- TEST 1: Watchlist Shell Mounting ---');
  watchlistView.render(testDiv);

  assert(testDiv.innerHTML.includes('watchlist-view-container'), 'Container has watchlist-view-container');
  assert(testDiv.innerHTML.includes('Watchlists'), 'Header contains Watchlists');
  assert(testDiv.innerHTML.includes('watchlistSelect'), 'Selector dropdown mounted');
  assert(testDiv.innerHTML.includes('newWatchlistBtn'), '+ New button mounted');
  assert(testDiv.innerHTML.includes('deleteWatchlistBtn'), 'Delete button mounted');
  assert(testDiv.innerHTML.includes('watchlistTickerInput'), 'Ticker input mounted');
  assert(testDiv.innerHTML.includes('watchlistAddBtn'), 'Add ticker button mounted');
  assert(testDiv.innerHTML.includes('watchlistValidationMsg'), 'Validation message element mounted');
  assert(testDiv.innerHTML.includes('watchlistGrid'), 'Tickers grid container mounted');
  assert(testDiv.innerHTML.includes('newWatchlistModal'), 'New Watchlist modal mounted');
  console.log('  ✓ PASS: Watchlist shell mounted cleanly with all required interactive elements');

  console.log('\n--- TEST 2: Ticker Rendering with Index Badges ---');
  watchlistView.watchlists = [
    {
      id: 'core_watchlist',
      name: 'Core Watchlist',
      tickers: [
        { ticker: 'NVDA', indices: ['S&P 500', 'Nasdaq 100', 'Dow 30'] },
        { ticker: 'SPY', indices: ['Major ETF'] },
        { ticker: 'POWL', indices: ['Russell 2000'] }
      ]
    }
  ];
  watchlistView.selectedWatchlistId = 'core_watchlist';

  const mockGrid = { innerHTML: '', querySelectorAll: () => [] };
  const mockBadge = { textContent: '' };
  watchlistView.container = {
    querySelector: (sel) => {
      if (sel === '#watchlistGrid') return mockGrid;
      if (sel === '#watchlistCountBadge') return mockBadge;
      return null;
    }
  };

  watchlistView.renderTickers();
  assert(mockBadge.textContent === '3 TICKERS', 'Count badge updated to 3 TICKERS');
  assert(mockGrid.innerHTML.includes('NVDA'), 'Grid contains NVDA');
  assert(mockGrid.innerHTML.includes('watchlist-index-badge sp500'), 'NVDA has S&P 500 badge');
  assert(mockGrid.innerHTML.includes('watchlist-index-badge ndx'), 'NVDA has Nasdaq 100 badge');
  assert(mockGrid.innerHTML.includes('Cockpit ↗'), 'Contains Cockpit drilldown button');
  assert(mockGrid.innerHTML.includes('watchlist-remove-btn'), 'Contains remove button');
  console.log('  ✓ PASS: Tickers rendered with authoritative index badges & action controls');

  console.log('\n--- TEST 3: Empty State Rendering ---');
  watchlistView.watchlists[0].tickers = [];
  watchlistView.renderTickers();
  assert(mockGrid.innerHTML.includes('watchlist-empty-state'), 'Empty state card rendered');
  assert(mockBadge.textContent === '0 TICKERS', 'Count badge updated to 0 TICKERS');
  console.log('  ✓ PASS: Empty state rendered cleanly when zero tickers present');

  console.log('\n--- TEST 4: Drilldown to Cockpit Interaction ---');
  let navigatedTab = null;
  let searchedTicker = null;
  global.window.quantApp = {
    tabManager: {
      switchTab: (tabId) => { navigatedTab = tabId; }
    },
    cockpitView: {
      searchTicker: (t) => { searchedTicker = t; }
    }
  };

  watchlistView.drillDownToCockpit('NVDA');
  assert.equal(navigatedTab, 'cockpit', 'Navigates to cockpit tab');
  assert.equal(searchedTicker, 'NVDA', 'Invokes cockpitView.searchTicker with NVDA');
  console.log('  ✓ PASS: Drilldown opens cockpit tab and auto-searches ticker');

  console.log('\n--- TEST 5: Lifecycle Teardown ---');
  watchlistView.destroy();
  assert.equal(watchlistView.container.innerHTML, '', 'destroy() cleared container');
  console.log('  ✓ PASS: Container successfully cleared on destroy');

  console.log('\n==================================================================');
  console.log('  ALL WATCHLIST VIEW TESTS PASSED (100% GREEN)');
  console.log('==================================================================');
}).catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
