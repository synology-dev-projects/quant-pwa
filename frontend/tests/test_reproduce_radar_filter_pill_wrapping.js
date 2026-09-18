import { strict as assert } from 'assert';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const radarJsPath = path.resolve(__dirname, '../src/tabs/radar_view.js');
const radarCssPath = path.resolve(__dirname, '../src/styles/radar.css');

assert(fs.existsSync(radarJsPath), `radar_view.js must exist at ${radarJsPath}`);
assert(fs.existsSync(radarCssPath), `radar.css must exist at ${radarCssPath}`);

const jsContent = fs.readFileSync(radarJsPath, 'utf8');
const cssContent = fs.readFileSync(radarCssPath, 'utf8');

console.log('--- REPRODUCTION CHECK 1: Filter Pills Markup & Badge Structure ---');
// Bug: Currently markup uses raw text parenthesis "ALL (<span id=\"radarCountAll\">0</span>)"
// which causes line breaks between label and "(" on mobile screens (375px-430px).
const hasRawParenthesesInMarkup = /ALL\s*\(\s*<span/i.test(jsContent) ||
  /WATCHLIST\s*\(\s*<span/i.test(jsContent) ||
  /FLOW LEADERS\s*\(\s*<span/i.test(jsContent);

if (hasRawParenthesesInMarkup) {
  assert.fail('REPRODUCED DEFECT: Filter pills contain raw parenthesis wrapping text which breaks across multiple lines on mobile screens.');
}

const hasPillBadgeSpans = jsContent.includes('class="radar-pill-badge" id="radarCountAll"') &&
  jsContent.includes('class="radar-pill-badge" id="radarCountWl"') &&
  jsContent.includes('class="radar-pill-badge" id="radarCountFlow"');

assert(hasPillBadgeSpans, 'Filter pills must use dedicated .radar-pill-badge elements for counts.');

console.log('--- REPRODUCTION CHECK 2: CSS white-space nowrap on .radar-filter-pill ---');
// Bug: .radar-filter-pill lacks white-space: nowrap causing awkward wrapping
const pillCssBlockMatch = cssContent.match(/\.radar-filter-pill\s*\{([^}]+)\}/);
assert(pillCssBlockMatch, '.radar-filter-pill rule must exist in radar.css');
const pillCssBlock = pillCssBlockMatch[1];

if (!pillCssBlock.includes('white-space: nowrap') && !pillCssBlock.includes('white-space:nowrap')) {
  assert.fail('REPRODUCED DEFECT: .radar-filter-pill lacks white-space: nowrap, causing filter text and counts to break onto new lines.');
}

console.log('--- REPRODUCTION CHECK 3: CSS .radar-pill-badge Styling ---');
const badgeCssMatch = cssContent.match(/\.radar-pill-badge\s*\{([^}]+)\}/);
assert(badgeCssMatch, '.radar-pill-badge style rule must exist in radar.css');
const badgeCss = badgeCssMatch[1];
assert(badgeCss.includes('border-radius: 9999px') || badgeCss.includes('border-radius:9999px'), '.radar-pill-badge must have capsule border-radius: 9999px');

console.log('--- REPRODUCTION CHECK 4: CSS white-space nowrap on .radar-session-tag ---');
const sessionTagMatch = cssContent.match(/\.radar-session-tag\s*\{([^}]+)\}/);
assert(sessionTagMatch, '.radar-session-tag rule must exist in radar.css');
const sessionTagCss = sessionTagMatch[1];
if (!sessionTagCss.includes('white-space: nowrap') && !sessionTagCss.includes('white-space:nowrap')) {
  assert.fail('REPRODUCED DEFECT: .radar-session-tag lacks white-space: nowrap, risking line wrap on narrow mobile viewports.');
}

console.log('--- REPRODUCTION CHECK 5: Mobile Responsive Filter Bar Rules ---');
const hasMobileMedia = cssContent.includes('@media') && cssContent.includes('.radar-filter-bar');
assert(hasMobileMedia, 'radar.css must include mobile @media responsive styling for .radar-filter-bar to handle mobile touch viewports.');

console.log('✅ ALL IN-SITU VERIFICATION CHECKS PASSED (GREEN)');
