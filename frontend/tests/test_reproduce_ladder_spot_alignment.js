import { strict as assert } from 'assert';

/**
 * RED GATE TEST:
 * Reproduces the Interactive Ladder Spot Placement Defect.
 * When spot is within a level's range (e.g. 7728.76 in 7728.00 - 7737.00):
 * 1. The spot marker must be positioned above that range row, not below it.
 * 2. The range row must receive the 'inside-zone' class and 'INSIDE ZONE' badge.
 */

// Mock basic browser globals for importing LevelsView
const _mockStorage = {};
global.window = {
  innerWidth: 1024,
  devicePixelRatio: 2,
  location: { origin: 'http://127.0.0.1:8000', hostname: '127.0.0.1', port: '8000' },
  localStorage: {
    getItem: (k) => _mockStorage[k] || null,
    setItem: (k, v) => { _mockStorage[k] = String(v); },
    removeItem: (k) => { delete _mockStorage[k]; }
  },
  addEventListener: () => {},
  removeEventListener: () => {}
};
global.localStorage = global.window.localStorage;
global.requestAnimationFrame = (cb) => { cb(); return 1; };
global.document = {
  createElement: () => ({
    tagName: 'DIV',
    style: {},
    children: [],
    appendChild: () => {},
    addEventListener: () => {}
  }),
  body: {}
};

async function run() {
  const { LevelsView } = await import('../src/tabs/levels_view.js');
  const view = new LevelsView();

  const levels = [
    {
      type: 'SELL',
      start_price: 7748.0,
      end_price: 7756.0,
      price_display: '7,748.00 - 7,756.00',
      comments: 'Major overhead resistance'
    },
    {
      type: 'SELL',
      start_price: 7728.0,
      end_price: 7737.0,
      price_display: '7,728.00 - 7,737.00',
      comments: 'Intraday sell corridor'
    },
    {
      type: 'BUY',
      start_price: 7718.0,
      end_price: 7722.0,
      price_display: '7,718.00 - 7,722.00',
      comments: 'Key support floor'
    }
  ];

  const spot = 7728.76;
  const html = view.buildLadderHtml(levels, spot, false);

  // Find index of spot marker and index of 7,728.00 - 7,737.00 row
  const spotMarkerIndex = html.indexOf('id="ladderSpotMarker"');
  const rangeRowIndex = html.indexOf('7,728.00 - 7,737.00');

  assert.ok(spotMarkerIndex !== -1, 'Spot marker must be present in ladder HTML');
  assert.ok(rangeRowIndex !== -1, 'Range row 7,728.00 - 7,737.00 must be present');

  // 1. Assert spot marker is positioned ABOVE (before) the 7728-7737 row
  assert.ok(
    spotMarkerIndex < rangeRowIndex,
    `Spot marker ($${spot}) must appear BEFORE 7,728.00 - 7,737.00 row. spotMarkerIndex=${spotMarkerIndex}, rangeRowIndex=${rangeRowIndex}`
  );

  // 2. Assert the 7728-7737 row is decorated with inside-zone class and badge
  assert.ok(
    html.includes('inside-zone'),
    'Range row containing the spot price must have class "inside-zone"'
  );
  assert.ok(
    html.includes('INSIDE ZONE'),
    'Range row containing the spot price must display "INSIDE ZONE" badge'
  );

  console.log('✅ Ladder spot alignment test passed');
}

run().catch((err) => {
  console.error('❌ Ladder spot alignment test failed (EXPECTED RED):', err.message);
  process.exit(1);
});
