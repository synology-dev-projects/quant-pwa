import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const appJsPath = path.resolve(__dirname, '../src/app.js');
const overviewJsPath = path.resolve(__dirname, '../src/tabs/overview_view.js');
const candlestickJsPath = path.resolve(__dirname, '../src/components/candlestick_chart.js');

const appSrc = fs.readFileSync(appJsPath, 'utf8');
const overviewSrc = fs.readFileSync(overviewJsPath, 'utf8');
const candlestickSrc = fs.readFileSync(candlestickJsPath, 'utf8');

// 1. Verify Tab 1 is Overview and standalone levels/macro tabs are removed
assert.ok(appSrc.includes("id: 'overview'"), 'app.js must register overview as a tab');
assert.ok(!appSrc.includes("id: 'levels'"), 'app.js must not register standalone levels tab');
assert.ok(!appSrc.includes("id: 'macro'"), 'app.js must not register standalone macro tab');
assert.ok(
  appSrc.includes("['overview', 'flow', 'cockpit', 'radar', 'watchlists']"),
  'app.js validTabs must match the 5-tab layout'
);

// 2. Verify OverviewView integrates LevelsView, MacroView, defaults, and localStorage persistence
assert.ok(overviewSrc.includes("DEFAULT_TICKERS = ['SPX', 'NDX', 'VIX', 'QQQ']"), 'Default tickers must be SPX, NDX, VIX, QQQ');
assert.ok(overviewSrc.includes("quant_overview_tickers"), 'Tickers must persist in localStorage');
assert.ok(overviewSrc.includes("hideCandlestick: true"), 'LevelsView must be embedded with hideCandlestick: true');
assert.ok(overviewSrc.includes("new MacroView()"), 'MacroView must be embedded in OverviewView');
assert.ok(overviewSrc.includes("/api/market/candles"), 'OverviewView must fetch /api/market/candles');

// 3. Verify CandlestickChart supports Intraday VWAP and Daily timeframe
assert.ok(candlestickSrc.includes("bar.vwap != null"), 'CandlestickChart must render VWAP when present');
assert.ok(candlestickSrc.includes("#22d3ee"), 'CandlestickChart must draw VWAP in cyan (#22d3ee)');
assert.ok(candlestickSrc.includes("this.timeframe === 'daily'"), 'CandlestickChart must support daily timeframe');

console.log('✅ test_overview_view.js passed!');
