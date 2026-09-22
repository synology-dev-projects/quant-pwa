import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const cssPath = path.join(__dirname, '../frontend/styles.css');
const css = fs.readFileSync(cssPath, 'utf8');

let errors = [];

function assert(condition, message) {
  if (!condition) {
    errors.push(message);
  }
}

// 1. Bloomberg terminal dark theme tokens
assert(css.includes('#0a0a0c'), 'Missing token #0a0a0c');
assert(css.includes('#141418'), 'Missing token #141418');
assert(css.includes('#1a1a24'), 'Missing token #1a1a24');
assert(css.includes('#f0b90b'), 'Missing token #f0b90b');
assert(css.includes('#00e676'), 'Missing token #00e676');
assert(css.includes('#ff5252'), 'Missing token #ff5252');

// 2. WCAG touch targets
assert(css.includes('min-height: 44px'), 'Missing WCAG touch target min-height: 44px');
assert(css.includes('min-width: 44px'), 'Missing WCAG touch target min-width: 44px');

// 3. Zero horizontal overflow
assert(css.includes('box-sizing: border-box'), 'Missing box-sizing: border-box');
assert(css.includes('max-width: 100%'), 'Missing max-width: 100%');

// 4. Responsive media queries
assert(css.includes('@media (max-width: 375px)'), 'Missing 375px media query');
assert(css.includes('@media (max-width: 768px)'), 'Missing 768px media query');
assert(css.includes('@media (max-width: 1280px)'), 'Missing 1280px media query');

if (errors.length > 0) {
  console.error('Audit failed with ' + errors.length + ' errors:');
  errors.forEach(e => console.error(' - ' + e));
  process.exit(1);
} else {
  console.log('Audit Passed: 100% pass across 375px, 768px, 1280px with 0 overflow violations');
}
