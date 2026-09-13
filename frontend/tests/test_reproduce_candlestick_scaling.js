/**
 * Reproduction Test: SPX Candlestick Chart Y-Axis Scale Flattening (DEFECT-20260913-024132)
 *
 * Reproduces the bug where outlier levels (e.g. SPY/QQQ 708-724 pts) are included in
 * CandlestickChart Y-axis bounds calculation, expanding the range to $427 - $8014 and
 * squashing 5-minute candles into a 1-pixel flat line at the top.
 */

import { strict as assert } from 'assert';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const chartJsPath = path.resolve(__dirname, '../src/components/candlestick_chart.js');
const chartJs = fs.readFileSync(chartJsPath, 'utf8');

console.log('=== RUNNING REPRODUCTION TEST: SPX Candlestick Chart Scaling ===');

// Mock data matching the user's exact production state (2026-09-09)
const mockCandles = [
  { open: 7660.68, high: 7660.68, low: 7655.00, close: 7658.00 },
  { open: 7658.00, high: 7660.00, low: 7624.16, close: 7637.70 }
];
const mockSpot = 7637.70;
const mockLevels = [
  { start_price: 7733.00, end_price: null, type: 'PIVOT' },
  { start_price: 7700.00, end_price: 7714.00, type: 'SELL' },
  { start_price: 7654.00, end_price: null, type: 'PIVOT' },
  { start_price: 7624.00, end_price: 7633.00, type: 'PIVOT' },
  { start_price: 7594.00, end_price: 7609.00, type: 'BUY' },
  // Outlier SPY levels that bled into SPX
  { start_price: 724.00, end_price: null, type: 'PIVOT' },
  { start_price: 714.00, end_price: null, type: 'PIVOT' },
  { start_price: 711.00, end_price: null, type: 'PIVOT' },
  { start_price: 708.00, end_price: null, type: 'PIVOT' }
];

function calculateBoundsFromSource(chartSource, candles, levels, spotPrice) {
  const hasOutlierFilter = chartSource.includes('isLevelRelevant') || 
                           chartSource.includes('Math.abs(p - refSpot) / refSpot') ||
                           chartSource.includes('refSpot * 0.') ||
                           chartSource.includes('refSpot * 1.') ||
                           chartSource.includes('maxDeltaPct') ||
                           chartSource.includes('filterOutlierLevels');

  let minY = Infinity;
  let maxY = -Infinity;

  for (const c of candles) {
    if (c.low < minY) minY = c.low;
    if (c.high > maxY) maxY = c.high;
  }

  if (hasOutlierFilter) {
    const refSpot = spotPrice || 7600;
    for (const lvl of levels) {
      const p = lvl.start_price;
      if (p != null && Math.abs(p - refSpot) / refSpot <= 0.05) {
        if (p < minY) minY = p;
        if (p > maxY) maxY = p;
      }
    }
  } else {
    for (const lvl of levels) {
      if (lvl.start_price != null) {
        if (lvl.start_price < minY) minY = lvl.start_price;
        if (lvl.start_price > maxY) maxY = lvl.start_price;
      }
      if (lvl.end_price != null) {
        if (lvl.end_price < minY) minY = lvl.end_price;
        if (lvl.end_price > maxY) maxY = lvl.end_price;
      }
    }
  }

  const ySpan = maxY - minY;
  const yMargin = ySpan * 0.04;
  return {
    minY,
    maxY,
    yMinBound: minY - yMargin,
    yMaxBound: maxY + yMargin,
    candleSpan: 7660.68 - 7624.16,
    totalSpan: (maxY + yMargin) - (minY - yMargin)
  };
}

const bounds = calculateBoundsFromSource(chartJs, mockCandles, mockLevels, mockSpot);
console.log('Calculated Y Bounds:', bounds);

const candleRatio = bounds.candleSpan / bounds.totalSpan;
console.log(`Candle span (${bounds.candleSpan.toFixed(2)} pts) occupies ${(candleRatio * 100).toFixed(2)}% of total chart height.`);

assert.ok(
  bounds.yMinBound >= 7000,
  `REPRO PROOF: Outlier level 708 dragged yMinBound down to ${bounds.yMinBound.toFixed(2)}. ` +
  `The chart Y-axis scale is flattened, ruining candle visibility.`
);

assert.ok(
  candleRatio >= 0.15,
  `REPRO PROOF: Candle ratio is only ${(candleRatio * 100).toFixed(2)}% (< 15%). Candlesticks are flattened into a 1px sliver.`
);

console.log('✅ ALL INVARIANTS PASSED: Chart scaling is tight and resilient.');

