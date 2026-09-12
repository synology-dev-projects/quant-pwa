import { AppState, fetchWithAuth } from './state.js?v=30';
import { TabManager } from './tabs/tab_manager.js?v=30';
import { CockpitView } from './tabs/cockpit_view.js?v=30';
import { RadarView } from './tabs/radar_view.js?v=31';
import { FlowView } from './tabs/flow_view.js?v=32';
import { WatchlistView } from './tabs/watchlist_view.js?v=33';
import { LevelsView } from './tabs/levels_view.js?v=34';
import { Lightbox } from './components/lightbox.js?v=30';
import { LockScreen } from './components/lock_screen.js?v=30';
import { SettingsModal } from './components/settings_modal.js?v=30';
import { DiagnosticsModal } from './components/diagnostics_modal.js?v=30';

class App {
  constructor() {
    this.cockpitView = new CockpitView();
    this.radarView = new RadarView();
    this.flowView = new FlowView();
    this.watchlistView = new WatchlistView();
    this.levelsView = new LevelsView();
    this.lightbox = new Lightbox();
    window.quantLightbox = this.lightbox;

    this.diagnosticsModal = new DiagnosticsModal();
    window.quantDiagnostics = this.diagnosticsModal;
    window.quantApp = this;

    this.tabManager = null;
    this.lockScreen = null;
    this.settingsModal = null;

    this.init();
  }

  async init() {
    this.initTabs();
    this.initLockScreen();
    this.initSettingsModal();
    this.registerServiceWorker();
    this.checkUpdateBanner();

    // Check 6-hour session authentication
    const isAuthenticated = await this.lockScreen.checkAuthentication();
    if (isAuthenticated) {
      this.onUnlocked();
    }
  }

  checkUpdateBanner() {
    const updatedVer = sessionStorage.getItem('quant_update_banner');
    if (updatedVer) {
      sessionStorage.removeItem('quant_update_banner');
      const toast = document.createElement('div');
      toast.className = 'update-success-toast';
      toast.innerHTML = `<span class="status-dot dot-live"></span> <span><b>Quant AI Updated:</b> Build ${updatedVer} is active &amp; verified fresh.</span>`;
      document.body.appendChild(toast);
      setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 400);
      }, 4000);
    }
  }

  initLockScreen() {
    this.lockScreen = new LockScreen(() => this.onUnlocked());
  }

  onUnlocked() {
    // Clear any stale unauthenticated caches
    if (this.cockpitView && this.cockpitView.dataCache) {
      this.cockpitView.dataCache.clear();
    }

    // If cockpit tab is active, re-fetch fresh data with valid session token
    if (AppState.getActiveTab() === 'cockpit' && this.cockpitView && this.cockpitView.currentTicker) {
      this.cockpitView.searchTicker(this.cockpitView.currentTicker);
    }
    if (this.radarView) {
      this.radarView.loadAvailableDates();
      if (AppState.getActiveTab() === 'radar') {
        this.radarView.loadScanData();
      }
    }
    if (this.flowView && AppState.getActiveTab() === 'flow') {
      this.flowView.loadFlowData();
    }
    if (this.watchlistView) {
      this.watchlistView.loadAvailableTickers();
      if (AppState.getActiveTab() === 'watchlists') {
        this.watchlistView.loadWatchlists();
      }
    }
    if (this.levelsView && AppState.getActiveTab() === 'levels') {
      this.levelsView.loadLevelsData();
    }
  }

  initTabs() {
    const tabBar = document.getElementById('tabBar');
    const tabContent = document.getElementById('tabContent');

    this.tabManager = new TabManager(tabBar, tabContent, (tabId) => {
      AppState.setActiveTab(tabId);
      if (tabId === 'radar' && this.radarView) {
        if (!this.radarView.currentData || !this.radarView.currentData.rows) {
          this.radarView.loadAvailableDates();
          this.radarView.loadScanData();
        }
      }
      if (tabId === 'flow' && this.flowView) {
        if (!this.flowView.currentData) {
          this.flowView.loadFlowData();
        }
      }
      if (tabId === 'levels' && this.levelsView) {
        if (!this.levelsView.currentData) {
          this.levelsView.loadInitialData();
        }
      }
      if (tabId === 'watchlists' && this.watchlistView) {
        if (!this.watchlistView.watchlists || this.watchlistView.watchlists.length === 0) {
          this.watchlistView.loadAvailableTickers();
          this.watchlistView.loadWatchlists();
        } else {
          this.watchlistView.startQuotePolling();
        }
      } else if (this.watchlistView) {
        this.watchlistView.stopQuotePolling();
      }
    });

    // 1. Options Flow Aggregate Tab
    this.tabManager.registerTab({
      id: 'flow',
      title: 'Flow',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"></path></svg>`,
      render: (container) => this.flowView.render(container)
    });

    // 2. Ticker Cockpit Tab
    this.tabManager.registerTab({
      id: 'cockpit',
      title: 'Cockpit',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"></rect><rect x="14" y="3" width="7" height="5"></rect><rect x="14" y="12" width="7" height="9"></rect><rect x="3" y="16" width="7" height="5"></rect></svg>`,
      render: (container) => this.cockpitView.render(container)
    });

    // 3. Confluence Radar Tab
    this.tabManager.registerTab({
      id: 'radar',
      title: 'Confluence Radar',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 10 10"></path><path d="M12 6a6 6 0 0 1 6 6"></path><circle cx="12" cy="2" r="2"></circle></svg>`,
      render: (container) => this.radarView.render(container)
    });

    // 4. Watchlists Tab
    this.tabManager.registerTab({
      id: 'watchlists',
      title: 'Watchlists',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>`,
      render: (container) => this.watchlistView.render(container)
    });

    // 5. SPX Quant Levels Tab (PWA-01 - Locked to SPX)
    this.tabManager.registerTab({
      id: 'levels',
      title: 'SPX Levels',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3v18M16 3v18M8 7h8M8 12h8M8 17h8"></path></svg>`,
      render: (container) => this.levelsView.render(container)
    });

    // Activate initial tab from localStorage
    const savedTab = AppState.getActiveTab();
    const validTabs = ['flow', 'cockpit', 'radar', 'watchlists', 'levels'];
    const activeTab = validTabs.includes(savedTab) ? savedTab : 'flow';
    this.tabManager.switchTab(activeTab);
  }

  initSettingsModal() {
    this.settingsModal = new SettingsModal({
      onSettingsChanged: () => {},
      onLockApp: () => {
        this.lockScreen?.show();
      }
    });
  }

  handleUnauthorized(message) {
    AppState.clearSession();
    if (this.lockScreen) {
      this.lockScreen.show();
      this.lockScreen.showError(message || 'Session expired. Please unlock the app.');
    }
  }

  registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('./sw.js').then((reg) => {
          reg.update();
          reg.onupdatefound = () => {
            const installingWorker = reg.installing;
            if (installingWorker) {
              installingWorker.onstatechange = () => {
                if (installingWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  // Promptly reload so user gets new tab
                  window.location.reload();
                }
              };
            }
          };
        }).catch((err) => {
          console.log('ServiceWorker registration failed: ', err);
        });
      });
    }
  }
}

// Bootstrap on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  new App();
});
