import { AppState, fetchWithAuth } from '../state.js?v=30';

export class WatchlistView {
  constructor() {
    this.container = null;
    this.watchlists = [];
    this.selectedWatchlistId = null;
    this.isLoading = false;
    this.quotes = {};
    this.pollInterval = null;
    this.visibilityHandler = null;
    this.availableTickers = [];
    this.sortColumn = 'symbol';
    this.sortDirection = 'asc';
    this._sessionExpiredBound = false;
  }

  render(container) {
    this.container = container;
    this.container.innerHTML = `
      <div class="watchlist-view-container">
        <!-- Top Bloomberg Header: Brand & Live Streaming Status -->
        <div class="watchlist-header-bar">
          <div class="watchlist-title-group">
            <span class="watchlist-badge-icon">📋</span>
            <h1 class="watchlist-title">WATCHLISTS</h1>
            <span class="watchlist-count-badge" id="watchlistCountBadge">0 TICKERS</span>
            <span class="watchlist-live-tag" id="watchlistLiveTag" title="Live quote feed (updates every 5s)">
              <span class="dot-live"></span> 5s LIVE
            </span>
          </div>

          <!-- Hidden select preserved for test fixture compatibility -->
          <select id="watchlistSelect" class="watchlist-select" style="display:none;" aria-label="Select Watchlist"></select>
        </div>

        <!-- 1-Tap Watchlist Pill Strip Switcher -->
        <div class="watchlist-pills-bar">
          <div class="watchlist-pills-strip" id="watchlistPillsStrip" role="tablist" aria-label="Watchlists tabs">
            <!-- Populated dynamically via renderWatchlistPills() -->
          </div>
          <div class="watchlist-pill-actions">
            <button type="button" class="watchlist-btn watchlist-btn-primary" id="newWatchlistBtn" title="Create New Watchlist">
              + New
            </button>
            <button type="button" class="watchlist-btn watchlist-btn-danger" id="deleteWatchlistBtn" title="Delete Active Watchlist">
              Delete
            </button>
          </div>
        </div>

        <!-- Compact Bloomberg Command Bar: Single-Row Ticker Entry -->
        <div class="watchlist-add-box">
          <form id="watchlistAddForm" class="watchlist-add-form" autocomplete="off">
            <div class="watchlist-input-wrapper">
              <span class="watchlist-terminal-prompt">&gt;</span>
              <input
                type="text"
                id="watchlistTickerInput"
                class="watchlist-input"
                placeholder="ENTER TICKER (e.g. NVDA, SPY)..."
                maxlength="12"
                autocomplete="off"
                autocapitalize="characters"
                spellcheck="false"
                list="watchlistTickerDatalist"
              />
              <datalist id="watchlistTickerDatalist"></datalist>
              <div id="watchlistAutocompleteMenu" class="watchlist-autocomplete-menu" style="display:none;"></div>
            </div>
            <button type="submit" id="watchlistAddBtn" class="watchlist-btn-add">
              <span>+ Add</span>
            </button>
          </form>
          <div id="watchlistValidationMsg" class="watchlist-validation-msg" role="status" aria-live="polite"></div>
        </div>

        <!-- Bloomberg Table Container -->
        <div id="watchlistGrid" class="watchlist-table-wrapper">
          <table class="quant-table watchlist-table">
            <thead class="watchlist-table-header" id="watchlistTableHeader">
              <tr>
                <th class="wth-col col-symbol sortable active" data-sort="symbol" scope="col" tabindex="0">
                  <div class="th-content">
                    <span>SYMBOL</span>
                    <span class="sort-glyph">▲</span>
                  </div>
                </th>
                <th class="wth-col col-indices sortable" data-sort="indices" scope="col" tabindex="0">
                  <div class="th-content">
                    <span>INDICES / EXCHANGE</span>
                    <span class="sort-glyph">⇅</span>
                  </div>
                </th>
                <th class="wth-col col-price sortable" data-sort="price" scope="col" tabindex="0">
                  <div class="th-content">
                    <span>LAST SPOT</span>
                    <span class="sort-glyph">⇅</span>
                  </div>
                </th>
                <th class="wth-col col-change sortable" data-sort="change" scope="col" tabindex="0">
                  <div class="th-content">
                    <span>24H CHG</span>
                    <span class="sort-glyph">⇅</span>
                  </div>
                </th>
                <th class="wth-col col-actions" scope="col">
                  <div class="th-content">
                    <span>ACTIONS</span>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody class="watchlist-table-body">
              <tr>
                <td colspan="5">
                  <div class="watchlist-empty-state">
                    <div class="watchlist-empty-icon">⏳</div>
                    <div class="watchlist-empty-title">Loading Watchlist...</div>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- New Watchlist Modal -->
      <div id="newWatchlistModal" class="watchlist-modal-overlay">
        <div class="watchlist-modal-card">
          <div class="watchlist-modal-header">
            <h3 class="watchlist-modal-title">New Watchlist</h3>
            <button type="button" id="closeWatchlistModalBtn" class="watchlist-modal-close" aria-label="Close modal">&times;</button>
          </div>
          <div class="watchlist-modal-body">
            <label for="newWatchlistNameInput" class="watchlist-modal-label">Watchlist Name</label>
            <input
              type="text"
              id="newWatchlistNameInput"
              class="watchlist-modal-input"
              placeholder="e.g. Tech Megacaps, Energy Momentum"
              maxlength="40"
            />
          </div>
          <div class="watchlist-modal-actions">
            <button type="button" id="cancelWatchlistModalBtn" class="watchlist-modal-btn-cancel">Cancel</button>
            <button type="button" id="confirmWatchlistModalBtn" class="watchlist-modal-btn-create">Create</button>
          </div>
        </div>
      </div>
    `;

    this.bindEvents();
    if (AppState && AppState.getSessionToken()) {
      this.loadWatchlists();
      this.loadAvailableTickers();
    } else {
      this.renderSessionExpiredState();
    }
  }

  bindEvents() {
    if (!this.container) return;

    // Watchlist Dropdown Select (synchronized fallback)
    const select = this.container?.querySelector?.('#watchlistSelect');
    if (select) {
      select.addEventListener('change', (e) => {
        this.selectedWatchlistId = e.target.value;
        this.clearValidationMessage();
        this.renderWatchlistPills();
        this.renderTickers();
        this.fetchQuotes();
      });
    }

    // Add Ticker Form
    const form = this.container?.querySelector?.('#watchlistAddForm');
    if (form) {
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const input = this.container?.querySelector?.('#watchlistTickerInput');
        if (!input) return;
        const ticker = input.value.trim().toUpperCase();
        if (!ticker) return;
        const autoMenu = this.container?.querySelector?.('#watchlistAutocompleteMenu');
        if (autoMenu) autoMenu.style.display = 'none';
        await this.addTicker(ticker);
      });
    }

    // Interactive Autocomplete Suggestions on Input
    const input = this.container?.querySelector?.('#watchlistTickerInput');
    const autoMenu = this.container?.querySelector?.('#watchlistAutocompleteMenu');
    if (input && autoMenu) {
      input.addEventListener('input', () => {
        const val = input.value.trim().toUpperCase();
        if (!val || !this.availableTickers || this.availableTickers.length === 0) {
          autoMenu.style.display = 'none';
          autoMenu.innerHTML = '';
          return;
        }
        const matches = this.availableTickers
          .filter(t => t.ticker.startsWith(val))
          .slice(0, 10);

        if (matches.length === 0) {
          autoMenu.style.display = 'none';
          autoMenu.innerHTML = '';
          return;
        }

        autoMenu.innerHTML = matches.map(m => `
          <div class="watchlist-autocomplete-item" data-ticker="${m.ticker}">
            <span class="auto-ticker">${m.ticker}</span>
            <span class="auto-indices">${(m.indices || []).join(' · ')}</span>
          </div>
        `).join('');
        autoMenu.style.display = 'block';

        autoMenu.querySelectorAll('.watchlist-autocomplete-item').forEach(item => {
          item.addEventListener('click', async () => {
            const t = item.getAttribute('data-ticker');
            if (t) {
              input.value = t;
              autoMenu.style.display = 'none';
              await this.addTicker(t);
            }
          });
        });
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && autoMenu) {
          autoMenu.style.display = 'none';
        }
      });

      if (typeof document !== 'undefined') {
        document.addEventListener('click', (e) => {
          if (!input.contains(e.target) && !autoMenu.contains(e.target)) {
            autoMenu.style.display = 'none';
          }
        });
      }
    }

    // New Watchlist Modal Triggers
    const newBtn = this.container?.querySelector?.('#newWatchlistBtn');
    const modal = this.container?.querySelector?.('#newWatchlistModal');
    const nameInput = this.container?.querySelector?.('#newWatchlistNameInput');
    const closeBtn = this.container?.querySelector?.('#closeWatchlistModalBtn');
    const cancelBtn = this.container?.querySelector?.('#cancelWatchlistModalBtn');
    const confirmBtn = this.container?.querySelector?.('#confirmWatchlistModalBtn');

    const openModal = () => {
      if (modal) {
        modal.classList.add('open');
        if (nameInput) {
          nameInput.value = '';
          setTimeout(() => nameInput.focus(), 50);
        }
      }
    };

    const closeModal = () => {
      if (modal) modal.classList.remove('open');
    };

    if (newBtn) newBtn.addEventListener('click', openModal);
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

    if (confirmBtn) {
      confirmBtn.addEventListener('click', async () => {
        const name = nameInput ? nameInput.value.trim() : '';
        if (!name) return;
        await this.createWatchlist(name);
        closeModal();
      });
    }

    if (nameInput) {
      nameInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const name = nameInput.value.trim();
          if (!name) return;
          await this.createWatchlist(name);
          closeModal();
        } else if (e.key === 'Escape') {
          closeModal();
        }
      });
    }

    // Delete Watchlist Button
    const deleteBtn = this.container?.querySelector?.('#deleteWatchlistBtn');
    if (deleteBtn) {
      deleteBtn.addEventListener('click', async () => {
        if (!this.selectedWatchlistId) return;
        const current = this.watchlists.find(w => w.id === this.selectedWatchlistId);
        const name = current ? current.name : 'this watchlist';
        const ok = (typeof window !== 'undefined' && window.confirm)
          ? window.confirm(`Are you sure you want to delete "${name}"?`)
          : true;
        if (ok) {
          await this.deleteWatchlist(this.selectedWatchlistId);
        }
      });
    }

    // Tab visibility handler for battery & network conservation
    if (!this.visibilityHandler && typeof document !== 'undefined') {
      this.visibilityHandler = () => {
        if (document.hidden) {
          this.stopQuotePolling();
        } else if (AppState && typeof AppState.getActiveTab === 'function' && AppState.getActiveTab() === 'watchlists') {
          this.startQuotePolling();
        }
      };
      document.addEventListener('visibilitychange', this.visibilityHandler);
    }

    // Session Expired Event Listeners
    if (!this._sessionExpiredBound && typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
      window.addEventListener('quant-session-expired', () => {
        this.stopQuotePolling();
        this.renderSessionExpiredState();
      });
      this._sessionExpiredBound = true;
    }
    if (AppState && typeof AppState.onSessionExpired === 'function') {
      AppState.onSessionExpired(() => {
        this.stopQuotePolling();
        this.renderSessionExpiredState();
      });
    }
  }

  showValidationMessage(msg, isError = false) {
    const el = this.container?.querySelector?.('#watchlistValidationMsg');
    if (!el) return;
    el.textContent = msg;
    el.className = `watchlist-validation-msg visible ${isError ? 'error' : 'success'}`;
  }

  clearValidationMessage() {
    const el = this.container?.querySelector?.('#watchlistValidationMsg');
    if (!el) return;
    el.textContent = '';
    el.className = 'watchlist-validation-msg';
  }

  async loadWatchlists() {
    this.isLoading = true;
    try {
      const gatewayUrl = AppState.getGatewayUrl();
      const res = await fetchWithAuth(`${gatewayUrl}/api/watchlists`);
      if (!res.ok) {
        throw new Error(`Failed to load watchlists (${res.status})`);
      }
      this.watchlists = await res.json();
      
      // Preserve selection or default to first
      if (!this.selectedWatchlistId || !this.watchlists.some(w => w.id === this.selectedWatchlistId)) {
        this.selectedWatchlistId = this.watchlists.length > 0 ? this.watchlists[0].id : null;
      }

      this.renderWatchlistSelect();
      this.renderTickers();
      this.startQuotePolling();
    } catch (err) {
      console.error('[Watchlist] Error loading watchlists:', err);
      if (err.message && (err.message.includes('401') || err.message.includes('SessionExpired'))) {
        this.stopQuotePolling();
        this.renderSessionExpiredState();
      } else {
        this.showValidationMessage(`Unable to load watchlists: ${err.message}`, true);
      }
    } finally {
      this.isLoading = false;
    }
  }

  async loadAvailableTickers() {
    try {
      const gatewayUrl = AppState.getGatewayUrl();
      const res = await fetchWithAuth(`${gatewayUrl}/api/watchlists/available-tickers`);
      if (res && res.ok) {
        const data = await res.json();
        this.availableTickers = Array.isArray(data) ? data : [];
        this.populateTickerDropdown();
      }
    } catch (err) {
      console.warn('[Watchlist] Could not load available tickers:', err);
    }
  }

  populateTickerDropdown() {
    const datalist = this.container?.querySelector?.('#watchlistTickerDatalist');
    if (datalist) {
      datalist.innerHTML = this.availableTickers.map(item => {
        const indicesStr = item.indices && item.indices.length > 0 ? ` (${item.indices.join(' · ')})` : '';
        return `<option value="${item.ticker}">${item.ticker}${indicesStr}</option>`;
      }).join('');
    }
  }

  renderWatchlistSelect() {
    const select = this.container?.querySelector?.('#watchlistSelect');
    if (select) {
      if (this.watchlists.length === 0) {
        select.innerHTML = '<option value="">No watchlists</option>';
      } else {
        select.innerHTML = this.watchlists
          .map(w => `<option value="${w.id}" ${w.id === this.selectedWatchlistId ? 'selected' : ''}>${w.name}</option>`)
          .join('');
      }
    }
    this.renderWatchlistPills();
  }

  renderWatchlistPills() {
    const strip = this.container?.querySelector?.('#watchlistPillsStrip');
    if (!strip) return;

    if (this.watchlists.length === 0) {
      strip.innerHTML = '<span class="watchlist-empty-pills">NO WATCHLISTS</span>';
      return;
    }

    strip.innerHTML = this.watchlists.map(w => {
      const isActive = w.id === this.selectedWatchlistId;
      const count = w.tickers ? w.tickers.length : 0;
      return `
        <button type="button" class="watchlist-pill ${isActive ? 'active' : ''}" data-id="${w.id}" role="tab" aria-selected="${isActive}">
          <span class="watchlist-pill-name">${w.name}</span>
          <span class="watchlist-pill-count">${count}</span>
        </button>
      `;
    }).join('');

    strip.querySelectorAll('.watchlist-pill').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const id = e.currentTarget.getAttribute('data-id');
        if (id && id !== this.selectedWatchlistId) {
          this.selectedWatchlistId = id;
          this.clearValidationMessage();
          this.renderWatchlistSelect();
          this.renderTickers();
          this.fetchQuotes();
        }
      });
    });
  }

  renderSessionExpiredState() {
    const grid = this.container?.querySelector?.('#watchlistGrid');
    if (!grid) return;
    grid.innerHTML = `
      <div class="watchlist-empty-state watchlist-session-expired">
        <div class="watchlist-empty-icon">🔒</div>
        <div class="watchlist-empty-title">Session Expired</div>
        <div class="watchlist-empty-desc">
          Institutional access requires an active terminal session. Tap below to unlock live watchlists.
        </div>
        <button type="button" class="watchlist-btn watchlist-btn-primary watchlist-unlock-btn" id="watchlistUnlockBtn">
          Unlock Terminal
        </button>
      </div>
    `;
    const unlockBtn = grid.querySelector?.('#watchlistUnlockBtn');
    if (unlockBtn) {
      unlockBtn.addEventListener('click', () => {
        if (typeof window !== 'undefined' && window.quantApp?.lockScreen) {
          window.quantApp.lockScreen.show();
        }
      });
    }
  }

  getSortGlyph(column) {
    if (this.sortColumn !== column) return '⇅';
    return this.sortDirection === 'asc' ? '▲' : '▼';
  }

  getAriaSort(column) {
    if (this.sortColumn !== column) return 'none';
    return this.sortDirection === 'asc' ? 'ascending' : 'descending';
  }

  handleSort(col) {
    if (this.sortColumn === col) {
      this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortColumn = col;
      this.sortDirection = (col === 'price' || col === 'change') ? 'desc' : 'asc';
    }
    this.renderTickers();
  }

  getSortedTickers(tickers) {
    if (!Array.isArray(tickers)) return [];
    const list = [...tickers];
    const dir = this.sortDirection === 'desc' ? -1 : 1;

    list.sort((a, b) => {
      if (this.sortColumn === 'symbol') {
        return dir * (a.ticker || '').localeCompare(b.ticker || '');
      }
      if (this.sortColumn === 'indices') {
        const strA = (a.indices || []).join(' ');
        const strB = (b.indices || []).join(' ');
        return dir * strA.localeCompare(strB);
      }
      if (this.sortColumn === 'price') {
        const qA = this.quotes[a.ticker]?.price;
        const qB = this.quotes[b.ticker]?.price;
        const valA = (typeof qA === 'number') ? qA : -Infinity;
        const valB = (typeof qB === 'number') ? qB : -Infinity;
        return dir * (valA - valB);
      }
      if (this.sortColumn === 'change') {
        const qA = this.quotes[a.ticker]?.change_pct;
        const qB = this.quotes[b.ticker]?.change_pct;
        const valA = (typeof qA === 'number') ? qA : -Infinity;
        const valB = (typeof qB === 'number') ? qB : -Infinity;
        return dir * (valA - valB);
      }
      return 0;
    });

    return list;
  }

  renderTickers() {
    const grid = this.container?.querySelector?.('#watchlistGrid');
    const badge = this.container?.querySelector?.('#watchlistCountBadge');
    if (!grid) return;

    const current = this.watchlists.find(w => w.id === this.selectedWatchlistId);
    const rawTickers = current?.tickers || [];
    const tickers = this.getSortedTickers(rawTickers);

    if (badge) {
      badge.textContent = `${tickers.length} TICKER${tickers.length === 1 ? '' : 'S'}`;
    }

    if (tickers.length === 0) {
      grid.innerHTML = `
        <div class="watchlist-empty-state">
          <div class="watchlist-empty-icon">📊</div>
          <div class="watchlist-empty-title">Watchlist is Empty</div>
          <div class="watchlist-empty-desc">
            Add a constituent of major US equity indices (S&amp;P 500, Nasdaq 100, Dow 30, Russell 2000, or Major ETFs) to track institutional exposure.
          </div>
        </div>
      `;
      return;
    }

    const rowsHtml = tickers.map(t => {
      const indexPills = (t.indices || []).map(idxName => {
        let cls = 'sp500';
        const lower = idxName.toLowerCase();
        if (lower.includes('nasdaq')) cls = 'ndx';
        else if (lower.includes('dow')) cls = 'dow';
        else if (lower.includes('russell')) cls = 'russell';
        else if (lower.includes('etf')) cls = 'etf';
        return `<span class="watchlist-index-badge ${cls}">${idxName}</span>`;
      }).join('');

      const q = this.quotes[t.ticker];
      const hasQuote = Boolean(q && typeof q.price === 'number');
      const displayPrice = hasQuote ? `$${q.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '--';
      let changeClass = 'neutral';
      let displayChange = '--';
      if (hasQuote && typeof q.change_pct === 'number') {
        if (q.change_pct > 0) {
          changeClass = 'positive';
          displayChange = `+${q.change_pct.toFixed(2)}%`;
        } else if (q.change_pct < 0) {
          changeClass = 'negative';
          displayChange = `${q.change_pct.toFixed(2)}%`;
        } else {
          changeClass = 'neutral';
          displayChange = '0.00%';
        }
      }

      return `
        <tr class="watchlist-ticker-card watchlist-table-row" data-ticker="${t.ticker}">
          <td class="col-symbol">
            <span class="watchlist-ticker-symbol" data-ticker="${t.ticker}" title="Open in Cockpit">${t.ticker}</span>
          </td>
          <td class="col-indices">
            <div class="watchlist-index-badges">
              ${indexPills}
            </div>
          </td>
          <td class="col-price">
            <div class="watchlist-card-price" id="watchlistPrice_${t.ticker}">
              <span class="watchlist-spot-price" id="spotPrice_${t.ticker}">${displayPrice}</span>
            </div>
          </td>
          <td class="col-change">
            <span class="watchlist-change-badge ${changeClass}" id="changeBadge_${t.ticker}">${displayChange}</span>
          </td>
          <td class="col-actions">
            <div class="watchlist-card-actions">
              <button type="button" class="watchlist-drilldown-btn" data-ticker="${t.ticker}" title="Inspect ${t.ticker} in Cockpit">
                Cockpit ↗
              </button>
              <button type="button" class="watchlist-remove-btn" data-ticker="${t.ticker}" title="Remove ${t.ticker}" aria-label="Remove ${t.ticker}">
                &times;
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    grid.innerHTML = `
      <table class="quant-table watchlist-table">
        <thead class="watchlist-table-header" id="watchlistTableHeader">
          <tr>
            <th class="wth-col col-symbol sortable ${this.sortColumn === 'symbol' ? 'active sort-' + this.sortDirection : ''}" data-sort="symbol" scope="col" tabindex="0" role="columnheader" aria-sort="${this.getAriaSort('symbol')}">
              <div class="th-content">
                <span>SYMBOL</span>
                <span class="sort-glyph">${this.getSortGlyph('symbol')}</span>
              </div>
            </th>
            <th class="wth-col col-indices sortable ${this.sortColumn === 'indices' ? 'active sort-' + this.sortDirection : ''}" data-sort="indices" scope="col" tabindex="0" role="columnheader" aria-sort="${this.getAriaSort('indices')}">
              <div class="th-content">
                <span>INDICES / EXCHANGE</span>
                <span class="sort-glyph">${this.getSortGlyph('indices')}</span>
              </div>
            </th>
            <th class="wth-col col-price sortable ${this.sortColumn === 'price' ? 'active sort-' + this.sortDirection : ''}" data-sort="price" scope="col" tabindex="0" role="columnheader" aria-sort="${this.getAriaSort('price')}">
              <div class="th-content">
                <span>LAST SPOT</span>
                <span class="sort-glyph">${this.getSortGlyph('price')}</span>
              </div>
            </th>
            <th class="wth-col col-change sortable ${this.sortColumn === 'change' ? 'active sort-' + this.sortDirection : ''}" data-sort="change" scope="col" tabindex="0" role="columnheader" aria-sort="${this.getAriaSort('change')}">
              <div class="th-content">
                <span>24H CHG</span>
                <span class="sort-glyph">${this.getSortGlyph('change')}</span>
              </div>
            </th>
            <th class="wth-col col-actions" scope="col" role="columnheader">
              <div class="th-content">
                <span>ACTIONS</span>
              </div>
            </th>
          </tr>
        </thead>
        <tbody class="watchlist-table-body">
          ${rowsHtml}
        </tbody>
      </table>
    `;

    // Attach sort header listeners
    grid.querySelectorAll?.('th.sortable')?.forEach(th => {
      th.addEventListener('click', () => {
        const col = th.getAttribute('data-sort');
        if (col) this.handleSort(col);
      });
      th.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          const col = th.getAttribute('data-sort');
          if (col) this.handleSort(col);
        }
      });
    });

    // Attach card/row event listeners
    grid.querySelectorAll?.('.watchlist-ticker-symbol, .watchlist-drilldown-btn')?.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const ticker = e.currentTarget.getAttribute('data-ticker');
        this.drillDownToCockpit(ticker);
      });
    });

    grid.querySelectorAll?.('.watchlist-remove-btn')?.forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const ticker = e.currentTarget.getAttribute('data-ticker');
        if (ticker) {
          await this.removeTicker(ticker);
        }
      });
    });
  }

  startQuotePolling() {
    this.updateLiveTag(true);
    this.fetchQuotes();
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
    }
    this.pollInterval = setInterval(() => {
      this.fetchQuotes();
    }, 5000);
  }

  stopQuotePolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.updateLiveTag(false);
  }

  updateLiveTag(isActive) {
    const tag = this.container?.querySelector?.('#watchlistLiveTag');
    if (!tag) return;
    if (isActive) {
      tag.className = 'watchlist-live-tag';
      tag.innerHTML = '<span class="dot-live"></span> 5s LIVE';
      tag.title = 'Live quote feed active (updates every 5s)';
    } else {
      tag.className = 'watchlist-live-tag paused';
      tag.innerHTML = '<span class="dot-live"></span> PAUSED';
      tag.title = 'Quote feed paused (inactive tab or backgrounded)';
    }
  }

  async fetchQuotes() {
    if (!this.selectedWatchlistId) return;
    if (typeof document !== 'undefined' && document.hidden) return;

    const current = this.watchlists.find(w => w.id === this.selectedWatchlistId);
    if (!current || !current.tickers || current.tickers.length === 0) return;

    const prevPrices = {};
    Object.keys(this.quotes).forEach(ticker => {
      if (this.quotes[ticker] && typeof this.quotes[ticker].price === 'number') {
        prevPrices[ticker] = this.quotes[ticker].price;
      }
    });

    try {
      const gatewayUrl = AppState.getGatewayUrl();
      const res = await fetchWithAuth(`${gatewayUrl}/api/watchlists/${this.selectedWatchlistId}/quotes`);
      if (!res.ok) return;

      const data = await res.json();
      if (data && data.quotes) {
        this.quotes = { ...this.quotes, ...data.quotes };
        this.updatePriceDisplays(prevPrices);
      }
    } catch (err) {
      if (err.message && (err.message.includes('401') || err.message.includes('SessionExpired'))) {
        this.stopQuotePolling();
        this.renderSessionExpiredState();
      }
    }
  }

  updatePriceDisplays(prevPrices = {}) {
    if (!this.container) return;

    Object.keys(this.quotes).forEach(ticker => {
      const q = this.quotes[ticker];
      if (!q || typeof q.price !== 'number') return;

      const spotEl = this.container?.querySelector?.(`#spotPrice_${ticker}`);
      const badgeEl = this.container?.querySelector?.(`#changeBadge_${ticker}`);

      if (spotEl) {
        const formattedPrice = `$${q.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        spotEl.textContent = formattedPrice;

        // Flash animation if price changed
        const prev = prevPrices[ticker];
        if (typeof prev === 'number') {
          if (q.price > prev) {
            spotEl.classList.remove('price-flash-green', 'price-flash-red');
            void spotEl.offsetWidth;
            spotEl.classList.add('price-flash-green');
          } else if (q.price < prev) {
            spotEl.classList.remove('price-flash-green', 'price-flash-red');
            void spotEl.offsetWidth;
            spotEl.classList.add('price-flash-red');
          }
        }
      }

      if (badgeEl && typeof q.change_pct === 'number') {
        if (q.change_pct > 0) {
          badgeEl.className = 'watchlist-change-badge positive';
          badgeEl.textContent = `+${q.change_pct.toFixed(2)}%`;
        } else if (q.change_pct < 0) {
          badgeEl.className = 'watchlist-change-badge negative';
          badgeEl.textContent = `${q.change_pct.toFixed(2)}%`;
        } else {
          badgeEl.className = 'watchlist-change-badge neutral';
          badgeEl.textContent = '0.00%';
        }
      }
    });
  }

  async addTicker(ticker) {
    if (!this.selectedWatchlistId) {
      this.showValidationMessage('Please select or create a watchlist first.', true);
      return;
    }

    const input = this.container?.querySelector?.('#watchlistTickerInput');
    const addBtn = this.container?.querySelector?.('#watchlistAddBtn');

    if (addBtn) addBtn.disabled = true;
    this.clearValidationMessage();

    try {
      const gatewayUrl = AppState.getGatewayUrl();
      const res = await fetchWithAuth(`${gatewayUrl}/api/watchlists/${this.selectedWatchlistId}/tickers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker })
      });

      const data = await res.json();

      if (res.status === 201) {
        if (input) input.value = '';
        const indexText = (data.indices && data.indices.length > 0) ? ` (${data.indices.join(' · ')})` : '';
        this.showValidationMessage(`✓ ${data.ticker} added successfully${indexText}.`, false);
        await this.loadWatchlists();
      } else if (res.status === 400) {
        this.showValidationMessage(`⚠ Validation Failed: ${data.detail || 'Symbol not in supported index.'}`, true);
      } else if (res.status === 409) {
        this.showValidationMessage(`⚠ ${ticker} is already present in this watchlist.`, true);
      } else {
        this.showValidationMessage(`⚠ ${data.detail || 'Error adding ticker.'}`, true);
      }
    } catch (err) {
      console.error('[Watchlist] Add ticker error:', err);
      this.showValidationMessage(`⚠ ${err.message}`, true);
    } finally {
      if (addBtn) addBtn.disabled = false;
    }
  }

  async removeTicker(ticker) {
    if (!this.selectedWatchlistId) return;

    try {
      const gatewayUrl = AppState.getGatewayUrl();
      const res = await fetchWithAuth(`${gatewayUrl}/api/watchlists/${this.selectedWatchlistId}/tickers/${encodeURIComponent(ticker)}`, {
        method: 'DELETE'
      });

      if (res.ok) {
        this.showValidationMessage(`Removed ${ticker}.`, false);
        await this.loadWatchlists();
      } else {
        const err = await res.json();
        this.showValidationMessage(`Error removing ticker: ${err.detail || res.statusText}`, true);
      }
    } catch (err) {
      console.error('[Watchlist] Remove ticker error:', err);
      this.showValidationMessage(`Error removing ticker: ${err.message}`, true);
    }
  }

  async createWatchlist(name) {
    try {
      const gatewayUrl = AppState.getGatewayUrl();
      const res = await fetchWithAuth(`${gatewayUrl}/api/watchlists`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to create watchlist');
      }

      const created = await res.json();
      this.selectedWatchlistId = created.id;
      this.showValidationMessage(`✓ Watchlist "${created.name}" created.`, false);
      await this.loadWatchlists();
    } catch (err) {
      console.error('[Watchlist] Create error:', err);
      this.showValidationMessage(`Error creating watchlist: ${err.message}`, true);
    }
  }

  async deleteWatchlist(id) {
    try {
      const gatewayUrl = AppState.getGatewayUrl();
      const res = await fetchWithAuth(`${gatewayUrl}/api/watchlists/${id}`, {
        method: 'DELETE'
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to delete watchlist');
      }

      this.selectedWatchlistId = null;
      this.showValidationMessage('Watchlist deleted.', false);
      await this.loadWatchlists();
    } catch (err) {
      console.error('[Watchlist] Delete error:', err);
      this.showValidationMessage(`Error deleting watchlist: ${err.message}`, true);
    }
  }

  drillDownToCockpit(ticker) {
    if (!ticker) return;
    if (typeof window !== 'undefined' && window.quantApp) {
      if (window.quantApp.tabManager) {
        window.quantApp.tabManager.switchTab('cockpit');
      }
      if (window.quantApp.cockpitView && typeof window.quantApp.cockpitView.searchTicker === 'function') {
        const input = (typeof document !== 'undefined' && typeof document.querySelector === 'function')
          ? document.querySelector('#cockpitSearchInput')
          : null;
        if (input) input.value = ticker;
        window.quantApp.cockpitView.searchTicker(ticker);
      }
    }
  }

  destroy() {
    this.stopQuotePolling();
    if (this.visibilityHandler && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', this.visibilityHandler);
      this.visibilityHandler = null;
    }
    if (this.container) {
      this.container.innerHTML = '';
    }
  }
}
