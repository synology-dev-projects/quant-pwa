const DEFAULT_TOOLS = [
  {
    name: 'get_gexdex',
    display: '/gex SPY',
    icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>`,
    title: 'Institutional GEX & DEX',
    description: 'Calculates institutional Gamma & Delta Exposure, Call/Put Walls, and Zero Gamma Flip points.',
    promptTemplate: '/gex SPY',
    params: [
      { name: 'ticker', type: 'string', required: true, desc: 'Stock ticker (e.g. SPY, NVDA, AAPL)' },
      { name: 'strike_range', type: 'int', required: false, desc: 'Strikes around spot (default: 25)' },
      { name: 'max_dte', type: 'int', required: false, desc: 'Max days to expiration (default: 50)' }
    ],
    example: '/gex NVDA'
  },
  {
    name: 'get_unusual_flow',
    display: '/flow',
    icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`,
    title: 'Institutional Options Flow',
    description: 'Queries 100% complete institutional options flow prints as an interactive paginated Bloomberg table (e.g. /flow Friday, /flow 2026-08-21, /flow 2026-08-17 to 2026-08-21). Defaults to latest session.',
    promptTemplate: '/flow',
    params: [
      { name: 'date', type: 'string', required: false, desc: 'Trading date (e.g. 2026-08-21, Friday) or range (e.g. 2026-08-17 to 2026-08-21). Defaults to latest.' }
    ],
    example: '/flow 2026-08-21 or /flow'
  },
  {
    name: 'get_strike_distribution',
    display: '/strikes NVDA',
    icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>`,
    title: 'Strike Distribution Matrix',
    description: 'Fetches granular strike-by-strike GEX/DEX distribution with multi-expiration breakdowns for interactive charts.',
    promptTemplate: '/strikes NVDA',
    params: [
      { name: 'ticker', type: 'string', required: true, desc: 'Stock ticker (e.g. NVDA, SPY, TSLA)' },
      { name: 'strike_range', type: 'int', required: false, desc: 'Strikes around spot (default: 25)' }
    ],
    example: '/strikes TSLA'
  },
  {
    name: 'get_market_status',
    display: '/market',
    icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`,
    title: 'Market Session Clock',
    description: 'Returns real-time US Equities market session status (pre-market, regular, after-hours, holiday).',
    promptTemplate: '/market',
    params: [],
    example: '/market'
  },
  {
    name: 'macro_schedule',
    display: '/macro',
    icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
    title: 'Macroeconomic Catalysts',
    description: 'Queries key economic releases, CPI, FOMC rate decisions, and volatility catalysts this week.',
    promptTemplate: '/macro',
    params: [],
    example: '/macro'
  }
];

export class PromptInput {
  constructor(container, onSubmit, onStop) {
    this.container = container;
    this.onSubmit = onSubmit;
    this.onStop = onStop;
    this.isStreaming = false;
    this.tools = [...DEFAULT_TOOLS];
    this.longPressTimer = null;
    this.activeTooltipBtn = null;

    this.render();
    this.initEvents();
    this.initTooltip();
    this.fetchMcpTools();
  }

  render() {
    this.container.innerHTML = `
      <div class="quick-chips-bar" id="quickChipsBar">
        ${this.renderChipsHtml()}
      </div>
      <div class="prompt-bar-container">
        <form class="prompt-form" id="promptForm">
          <textarea
            class="prompt-textarea"
            id="promptTextarea"
            rows="1"
            placeholder="Ask about GEX, Put/Call Walls, market levels..."
          ></textarea>
          <button type="submit" class="prompt-send-btn" id="sendBtn" title="Send message">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="19" x2="12" y2="5"></line>
              <polyline points="5 12 12 5 19 12"></polyline>
            </svg>
          </button>
          <button type="button" class="prompt-stop-btn" id="stopBtn" style="display:none;" title="Stop generating">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <rect x="4" y="4" width="16" height="16" rx="2"></rect>
            </svg>
          </button>
        </form>
      </div>
    `;

    this.chipsBar = this.container.querySelector('#quickChipsBar');
    this.textarea = this.container.querySelector('#promptTextarea');
    this.form = this.container.querySelector('#promptForm');
    this.sendBtn = this.container.querySelector('#sendBtn');
    this.stopBtn = this.container.querySelector('#stopBtn');
  }

  renderChipsHtml() {
    return this.tools.map((tool, index) => `
      <button
        type="button"
        class="skill-chip"
        data-index="${index}"
        data-prompt="${tool.promptTemplate}"
        title="${tool.title}"
      >
        <span class="skill-chip-icon">${tool.icon}</span>
        <span class="skill-chip-name">${tool.display}</span>
        <span class="skill-chip-pulse"></span>
      </button>
    `).join('');
  }

  initTooltip() {
    let tooltip = document.getElementById('skillTooltip');
    if (!tooltip) {
      tooltip = document.createElement('div');
      tooltip.id = 'skillTooltip';
      tooltip.className = 'skill-tooltip-card';
      document.body.appendChild(tooltip);
    }
    this.tooltip = tooltip;
  }

  initEvents() {
    // Auto-resize textarea
    this.textarea.addEventListener('input', () => {
      this.textarea.style.height = 'auto';
      this.textarea.style.height = `${Math.min(this.textarea.scrollHeight, 120)}px`;
    });

    // Enter to submit (Shift+Enter for newline)
    this.textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.submit();
      }
    });

    // Form submit
    this.form.addEventListener('submit', (e) => {
      e.preventDefault();
      this.submit();
    });

    // Stop button
    this.stopBtn.addEventListener('click', () => {
      if (this.onStop) this.onStop();
    });

    // Attach skill chip interactions
    this.bindChipEvents();

    // Global dismiss for tooltips on outside click/scroll
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.skill-chip') && !e.target.closest('#skillTooltip')) {
        this.hideTooltip();
      }
    });
    window.addEventListener('scroll', () => this.hideTooltip(), { passive: true });
  }

  bindChipEvents() {
    const chips = this.chipsBar.querySelectorAll('.skill-chip');
    chips.forEach((btn) => {
      const idx = parseInt(btn.getAttribute('data-index'), 10);
      const tool = this.tools[idx];
      if (!tool) return;

      // 1. Click-to-Insert and Focus
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        this.hideTooltip();
        this.insertPrompt(tool.promptTemplate);
      });

      // 2. Desktop Hover (mouseenter / mouseleave)
      btn.addEventListener('mouseenter', () => {
        this.showTooltip(tool, btn);
      });
      btn.addEventListener('mouseleave', () => {
        this.hideTooltip();
      });

      // 3. Mobile Touch (Long-Press for tooltip, tap to insert)
      btn.addEventListener('touchstart', (e) => {
        this.longPressTimer = setTimeout(() => {
          this.showTooltip(tool, btn);
          if (navigator.vibrate) navigator.vibrate(25);
        }, 380);
      }, { passive: true });

      btn.addEventListener('touchend', () => {
        if (this.longPressTimer) {
          clearTimeout(this.longPressTimer);
          this.longPressTimer = null;
        }
      });

      btn.addEventListener('touchmove', () => {
        if (this.longPressTimer) {
          clearTimeout(this.longPressTimer);
          this.longPressTimer = null;
        }
      });
    });
  }

  showTooltip(tool, btnElement) {
    if (!this.tooltip) return;

    const paramsHtml = tool.params && tool.params.length > 0
      ? `<div class="st-params-section">
           <div class="st-params-title">PARAMETERS</div>
           <div class="st-params-list">
             ${tool.params.map(p => `
               <div class="st-param-row">
                 <span class="st-param-tag ${p.required ? 'required' : 'optional'}">${p.name} ${p.required ? '*' : ''}</span>
                 <span class="st-param-desc">${p.desc || p.type}</span>
               </div>
             `).join('')}
           </div>
         </div>`
      : '';

    const exampleHtml = tool.example
      ? `<div class="st-example-section">
           <span class="st-example-lbl">QUICK PROMPT:</span>
           <code class="st-example-chip">${tool.example}</code>
         </div>`
      : '';

    this.tooltip.innerHTML = `
      <div class="st-header">
        <div class="st-title-group">
          <span class="st-icon">${tool.icon}</span>
          <span class="st-title">${tool.title}</span>
        </div>
        <span class="st-mcp-badge">MCP Skill</span>
      </div>
      <div class="st-desc">${tool.description}</div>
      ${paramsHtml}
      ${exampleHtml}
      <div class="st-footer-hint">Click to insert into chat</div>
    `;

    this.tooltip.classList.add('visible');

    // Position above the chip button
    const rect = btnElement.getBoundingClientRect();
    const tooltipRect = this.tooltip.getBoundingClientRect();

    let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
    let top = rect.top - tooltipRect.height - 10;

    // Viewport clamping
    const pad = 12;
    if (left < pad) left = pad;
    if (left + tooltipRect.width > window.innerWidth - pad) {
      left = window.innerWidth - tooltipRect.width - pad;
    }

    if (top < pad) {
      // If no room above, flip below
      top = rect.bottom + 10;
    }

    this.tooltip.style.left = `${Math.round(left)}px`;
    this.tooltip.style.top = `${Math.round(top)}px`;
    this.activeTooltipBtn = btnElement;
  }

  hideTooltip() {
    if (this.tooltip) {
      this.tooltip.classList.remove('visible');
    }
    this.activeTooltipBtn = null;
  }

  insertPrompt(promptText) {
    this.textarea.value = `${promptText} `;
    this.textarea.style.height = 'auto';
    this.textarea.style.height = `${Math.min(this.textarea.scrollHeight, 120)}px`;
    this.textarea.focus();
    // Move cursor to end
    this.textarea.setSelectionRange(this.textarea.value.length, this.textarea.value.length);
  }

  async fetchMcpTools() {
    try {
      const res = await fetch('/mcp/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: Date.now(),
          method: 'tools/list',
          params: {}
        })
      });
      if (res.ok) {
        const data = await res.json();
        if (data?.result?.tools && Array.isArray(data.result.tools)) {
          this.processMcpTools(data.result.tools);
        }
      }
    } catch (e) {
      console.debug('Dynamic MCP tool sync fallback to defaults', e);
    }
  }

  processMcpTools(mcpTools) {
    const iconMap = {
      'get_gexdex': { icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>`, display: '/gex SPY', example: '/gex NVDA' },
      'get_unusual_flow': { icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`, display: '/flow', example: '/flow 2026-08-21 or /flow' },
      'get_strike_distribution': { icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>`, display: '/strikes NVDA', example: '/strikes TSLA' },
      'get_market_status': { icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`, display: '/market', example: '/market' }
    };

    const syncedTools = [];

    mcpTools.forEach((tool) => {
      const meta = iconMap[tool.name] || {
        icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
        display: `/${tool.name.replace(/^get_/, '')}`,
        example: `/${tool.name.replace(/^get_/, '')}`
      };

      const requiredProps = tool.inputSchema?.required || [];
      const properties = tool.inputSchema?.properties || {};
      const params = Object.keys(properties).map(key => ({
        name: key,
        type: properties[key].type || 'string',
        required: requiredProps.includes(key),
        desc: properties[key].description || ''
      }));

      syncedTools.push({
        name: tool.name,
        display: meta.display,
        icon: meta.icon,
        title: tool.name.replace(/^get_/, '').replace(/_/g, ' ').toUpperCase(),
        description: tool.description,
        promptTemplate: meta.display,
        params: params,
        example: meta.example
      });
    });

    // Always ensure unusual options flow chip is present
    if (!syncedTools.some(t => t.name === 'get_unusual_flow')) {
      const flowDefault = DEFAULT_TOOLS.find(t => t.name === 'get_unusual_flow');
      if (flowDefault) syncedTools.splice(1, 0, flowDefault);
    }

    // Always ensure macro catalyst chip is present
    if (!syncedTools.some(t => t.name === 'macro_schedule')) {
      syncedTools.push({
        name: 'macro_schedule',
        display: '/macro',
        icon: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`,
        title: 'Macro Catalysts',
        description: 'Queries key economic releases, CPI, FOMC rate decisions, and volatility catalysts this week.',
        promptTemplate: '/macro',
        params: [],
        example: '/macro'
      });
    }

    this.tools = syncedTools;
    this.chipsBar.innerHTML = this.renderChipsHtml();
    this.bindChipEvents();
  }

  submit() {
    const text = this.textarea.value.trim();
    if (!text || this.isStreaming) return;

    this.textarea.value = '';
    this.textarea.style.height = 'auto';
    if (this.onSubmit) this.onSubmit(text);
  }

  setStreaming(streaming) {
    this.isStreaming = streaming;
    if (streaming) {
      this.sendBtn.style.display = 'none';
      this.stopBtn.style.display = 'flex';
      this.textarea.disabled = true;
    } else {
      this.sendBtn.style.display = 'flex';
      this.stopBtn.style.display = 'none';
      this.textarea.disabled = false;
      this.textarea.focus();
    }
  }
}
