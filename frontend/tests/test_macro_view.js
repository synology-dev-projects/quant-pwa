import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

console.log('==================================================================');
console.log('  PROBING QUANT PWA MACRO VIEW & ACCORDION (MACRO-01)');
console.log('==================================================================');

let passed = 0;
let failed = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  ✓ PASS: ${message}`);
    passed++;
  } else {
    console.error(`  ❌ FAIL: ${message}`);
    failed++;
  }
}

// 1. Verify file exists
const macroViewPath = path.join(__dirname, '../src/tabs/macro_view.js');
assert(fs.existsSync(macroViewPath), 'macro_view.js exists in src/tabs');

const content = fs.readFileSync(macroViewPath, 'utf8');

// 2. Class definition & methods
assert(content.includes('export class MacroView'), 'MacroView class exported');
assert(content.includes('formatCountdown('), 'formatCountdown method present');
assert(content.includes('getCountryFlag('), 'getCountryFlag method present');
assert(content.includes('getFilteredEvents('), 'getFilteredEvents method present');
assert(content.includes('renderEventCards('), 'renderEventCards method present');

// 3. Flag mappings
assert(content.includes("USD: '🇺🇸'"), 'USD flag emoji mapped');
assert(content.includes("EUR: '🇪🇺'"), 'EUR flag emoji mapped');
assert(content.includes("GBP: '🇬🇧'"), 'GBP flag emoji mapped');
assert(content.includes("JPY: '🇯🇵'"), 'JPY flag emoji mapped');

// 4. Accordion click handling
assert(content.includes("card.classList.toggle('expanded')"), 'Accordion toggle class implemented');

// 5. CSS styles verification
const stylesPath = path.join(__dirname, '../styles.css');
const styles = fs.readFileSync(stylesPath, 'utf8');

assert(styles.includes('.macro-view-container'), '.macro-view-container CSS defined');
assert(styles.includes('.macro-event-card'), '.macro-event-card CSS defined');
assert(styles.includes('.macro-event-card.expanded .macro-card-body'), 'Accordion expanded body CSS defined');
assert(styles.includes('.macro-filter-chip'), '.macro-filter-chip CSS defined');
assert(styles.includes('min-height: 44px;'), 'Interactive touch target satisfies min 44px');

console.log('==================================================================');
console.log(`  MACRO VIEW TESTS: ${passed} PASSED, ${failed} FAILED`);
console.log('==================================================================');

if (failed > 0) {
  process.exit(1);
}
