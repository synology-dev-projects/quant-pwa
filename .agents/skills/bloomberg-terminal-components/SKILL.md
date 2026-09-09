---
name: bloomberg-terminal-components
description: >-
  Scaffolds modular, production-ready Bloomberg-terminal dark UI components
  for Quant PWA. Enforces zero horizontal overflow, responsive layouts
  (375px/768px/1280px), and terminal typography tokens.
  Use when building UI cards, tables, ribbons, strike ladders, or running /scaffold-ui.
---

# 📊 Bloomberg Terminal UI Components (`/scaffold-ui`, `/terminal-ui`)

All UI in Quant PWA adheres to the **Bloomberg Terminal Dark Theme** with zero horizontal overflow across all responsive viewports (Mobile 375px, Tablet 768px, Desktop 1280px).

---

## 1. Design System Color Tokens

| Role | Hex Code | Usage |
| :--- | :--- | :--- |
| **Terminal Background** | `#0b0f19` / `#0f172a` | Body and card backdrops |
| **Card Surface** | `rgba(15, 23, 42, 0.75)` | Floating glassmorphism cards with `backdrop-filter: blur(12px)` |
| **Subtle Border** | `#1e293b` / `rgba(51, 65, 85, 0.4)` | 1px clean divider lines |
| **Bullish / Premium** | `#10b981` / `#34d399` | Calls, positive delta, high premium highlights |
| **Bearish / Puts** | `#ef4444` / `#f87171` | Puts, negative delta, hedge flow |
| **Speculation / OTM**| `#fbbf24` / `#f59e0b` | High OTM %, short-dated speculation |
| **Terminal Accent** | `#38bdf8` / `#60a5fa` | Primary focus, active tabs, ticker badges |

---

## 2. Component Scaffolder Templates

### A. Metric Ribbon (4-Column Responsive Grid)
```html
<div class="quant-metric-strip">
  <div class="quant-metric-tile">
    <span class="metric-label">SPOT PRICE</span>
    <span class="metric-val">$217.50</span>
    <span class="metric-sub delta-bull">+1.4% Today</span>
  </div>
  <div class="quant-metric-tile">
    <span class="metric-label">ZERO FLIP</span>
    <span class="metric-val">$214.00</span>
    <span class="metric-sub">Support Line</span>
  </div>
  <div class="quant-metric-tile">
    <span class="metric-label">CALL WALL</span>
    <span class="metric-val val-call">$230.00</span>
    <span class="metric-sub">Major Resistance</span>
  </div>
  <div class="quant-metric-tile">
    <span class="metric-label">PUT WALL</span>
    <span class="metric-val val-put">$200.00</span>
    <span class="metric-sub">Structural Floor</span>
  </div>
</div>
```

### B. High-Visibility Terminal Card (e.g. Notable Flow / Scanner)
```html
<div class="terminal-card">
  <div class="terminal-card-header">
    <span class="terminal-header-icon">💰</span>
    <div class="terminal-header-titles">
      <span class="terminal-card-title">TOP INSTITUTIONAL FLOW</span>
      <span class="terminal-card-subtitle">Prints > $1.0M Premium</span>
    </div>
    <span class="terminal-badge">LIVE</span>
  </div>
  <div class="terminal-card-body">
    <div class="terminal-row" data-ticker="NVDA">
      <div class="terminal-sym-cell">
        <span class="terminal-ticker">NVDA</span>
        <span class="terminal-pill pill-rank">1st</span>
      </div>
      <div class="terminal-metric-cell">
        <span class="terminal-val val-bull">$15.5M</span>
        <span class="terminal-unit">PREMIUM</span>
      </div>
    </div>
  </div>
</div>
```

---

## 3. Mandatory Responsive & Zero-Overflow Invariants

Every newly scaffolded component MUST enforce:
1. `box-sizing: border-box;` on all wrappers, columns, and tiles.
2. Parent container enforces `overflow-x: hidden;` or wraps wide tables in `.quant-table-wrapper` with `overflow-x: auto;`.
3. Action buttons must have minimum tap targets of **$44 \times 44\text{px}$** to satisfy WCAG mobile accessibility.
4. Verify by running:
   ```bash
   node frontend/tests/audit_layout.js
   ```
