/**
 * Reproduction Test: SPX Quant Levels Tab Scroll Blocked (DEFECT-20260912-212713)
 *
 * Verifies that .levels-container enforces vertical scrolling (overflow-y: auto,
 * -webkit-overflow-scrolling: touch, overflow-x: hidden, height: 100%) inside .tab-pane
 * (which enforces overflow: hidden), allowing the interactive price ladder, structured table,
 * and candlestick chart to scroll seamlessly.
 */

import { strict as assert } from 'assert';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const levelsCssPath = path.resolve(__dirname, '../src/styles/levels.css');
const levelsCss = fs.readFileSync(levelsCssPath, 'utf8');

function parseRule(css, selector) {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const regex = new RegExp(`${selector.replace('.', '\\.')}\\s*\\{([^\\}]+)\\}`, 'g');
  let match;
  const props = {};
  while ((match = regex.exec(clean)) !== null) {
    const body = match[1];
    const decls = body.split(';');
    for (const d of decls) {
      const idx = d.indexOf(':');
      if (idx !== -1) {
        const prop = d.slice(0, idx).trim().toLowerCase();
        const val = d.slice(idx + 1).trim();
        props[prop] = val;
      }
    }
  }
  return props;
}

console.log('=== RUNNING REPRODUCTION TEST: SPX Levels Tab Scrolling ===');

const containerProps = parseRule(levelsCss, '.levels-container');
console.log('Parsed .levels-container properties:', containerProps);

// Invariant 1: .levels-container must have overflow-y: auto to allow vertical scrolling within .tab-pane
assert.equal(
  containerProps['overflow-y'],
  'auto',
  `REPRO PROOF: .levels-container lacks overflow-y: auto (actual: ${containerProps['overflow-y'] || 'none/visible'}). ` +
  `Since parent .tab-pane has overflow: hidden, vertical scrolling is blocked.`
);

// Invariant 2: .levels-container must have height: 100% or flex: 1 1 0% with min-height: 0 to fill parent pane
assert.ok(
  containerProps['height'] === '100%' || (containerProps['flex'] && containerProps['flex'].includes('1 1')),
  `REPRO PROOF: .levels-container must define height: 100% or flex: 1 1 0% to bind to parent viewport (actual height: ${containerProps['height']}, flex: ${containerProps['flex']})`
);

// Invariant 3: .levels-container must have overflow-x: hidden to isolate horizontal bounds
assert.equal(
  containerProps['overflow-x'],
  'hidden',
  `REPRO PROOF: .levels-container must enforce overflow-x: hidden to prevent horizontal jitter.`
);

// Invariant 4: .levels-container must have -webkit-overflow-scrolling: touch for iOS/mobile PWA momentum scrolling
assert.equal(
  containerProps['-webkit-overflow-scrolling'],
  'touch',
  `REPRO PROOF: .levels-container lacks -webkit-overflow-scrolling: touch for mobile momentum scroll.`
);

console.log('✅ ALL INVARIANTS PASSED: SPX Levels Tab scrolling is correctly enabled.');
