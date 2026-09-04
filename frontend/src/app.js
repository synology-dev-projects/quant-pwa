import { AppState, fetchWithAuth } from './state.js?v=30';
import { TabManager } from './tabs/tab_manager.js?v=30';
import { ChatView } from './tabs/chat_view.js?v=30';
import { CockpitView } from './tabs/cockpit_view.js?v=30';
import { RadarView } from './tabs/radar_view.js?v=30';
import { PromptInput } from './components/prompt_input.js?v=30';
import { Lightbox } from './components/lightbox.js?v=30';
import { LockScreen } from './components/lock_screen.js?v=30';
import { SettingsModal } from './components/settings_modal.js?v=30';
import { DiagnosticsModal } from './components/diagnostics_modal.js?v=30';

const AVAILABLE_MODELS = [
  { id: 'gemini-3.5-flash-lite', name: 'Gemini 3.5 Flash-Lite' },
  { id: 'gemini-3.7-flash', name: 'Gemini 3.7 Flash' },
  { id: 'gemini-3.6-flash', name: 'Gemini 3.6 Flash' },
  { id: 'gemini-flash-latest', name: 'Gemini Flash Latest' }
];

class App {
  constructor() {
    this.chatView = new ChatView();
    this.cockpitView = new CockpitView();
    this.radarView = new RadarView();
    this.lightbox = new Lightbox();
    window.quantLightbox = this.lightbox;

    this.diagnosticsModal = new DiagnosticsModal();
    window.quantDiagnostics = this.diagnosticsModal;
    window.quantApp = this;

    this.activeAbortController = null;
    this.tabManager = null;
    this.promptInput = null;
    this.lockScreen = null;
    this.settingsModal = null;

    this.init();
  }

  async init() {
    this.initTabs();
    this.initLockScreen();
    this.initSettingsModal();
    this.initPromptBar();
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
    this.initModelSelector();

    // Clear any stale unauthenticated caches
    if (this.cockpitView && this.cockpitView.dataCache) {
      this.cockpitView.dataCache.clear();
    }

    // If cockpit tab is active, re-fetch fresh data with valid session token
    if (AppState.getActiveTab() === 'cockpit' && this.cockpitView && this.cockpitView.currentTicker) {
      this.cockpitView.searchTicker(this.cockpitView.currentTicker);
    }
    if (AppState.getActiveTab() === 'radar' && this.radarView) {
      this.radarView.loadScanData();
    }

    // Load initial chat history
    const history = AppState.getHistory();
    this.chatView.loadHistory(history);
  }

  initTabs() {
    const tabBar = document.getElementById('tabBar');
    const tabContent = document.getElementById('tabContent');
    const promptContainer = document.getElementById('promptContainer');

    this.tabManager = new TabManager(tabBar, tabContent, (tabId) => {
      AppState.setActiveTab(tabId);
      if (promptContainer) {
        promptContainer.style.display = (tabId === 'cockpit' || tabId === 'radar') ? 'none' : 'block';
      }
    });

    // 1. Ticker Cockpit Tab
    this.tabManager.registerTab({
      id: 'cockpit',
      title: 'Cockpit',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"></rect><rect x="14" y="3" width="7" height="5"></rect><rect x="14" y="12" width="7" height="9"></rect><rect x="3" y="16" width="7" height="5"></rect></svg>`,
      render: (container) => this.cockpitView.render(container)
    });

    // 2. Confluence Radar Tab
    this.tabManager.registerTab({
      id: 'radar',
      title: 'Confluence Radar',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 10 10"></path><path d="M12 6a6 6 0 0 1 6 6"></path><circle cx="12" cy="12" r="2"></circle></svg>`,
      render: (container) => this.radarView.render(container)
    });

    // 3. Chat Stream Tab
    this.tabManager.registerTab({
      id: 'chat',
      title: 'Chat Stream',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`,
      render: (container) => this.chatView.render(container)
    });

    // Activate initial tab from localStorage
    const savedTab = AppState.getActiveTab();
    this.tabManager.switchTab(savedTab);
  }

  initPromptBar() {
    const promptContainer = document.getElementById('promptContainer');
    this.promptInput = new PromptInput(
      promptContainer,
      (text) => this.handleUserPrompt(text),
      () => this.stopGenerating()
    );
  }

  async initModelSelector() {
    const modelSelect = document.getElementById('modelSelect');
    if (!modelSelect) return;

    let models = AVAILABLE_MODELS;

    // Dynamically load available models from Gateway using fetchWithAuth
    try {
      const gatewayBase = AppState.getGatewayUrl() || '';
      const res = await fetchWithAuth(`${gatewayBase}/api/models`);
      if (res.ok) {
        const data = await res.json();
        if (data.models && Array.isArray(data.models)) {
          models = data.models;
        }
      }
    } catch (e) {
      console.warn('Using fallback models list:', e);
    }

    const currentModel = AppState.getModel();
    modelSelect.innerHTML = models.map(m =>
      `<option value="${m.id}" ${m.id === currentModel ? 'selected' : ''}>${m.name}</option>`
    ).join('');

    // If current model is not in list, default to gemini-3.5-flash-lite
    if (!models.some(m => m.id === currentModel)) {
      AppState.setModel('gemini-3.5-flash-lite');
      modelSelect.value = 'gemini-3.5-flash-lite';
    } else {
      modelSelect.value = currentModel;
    }

    modelSelect.addEventListener('change', (e) => {
      AppState.setModel(e.target.value);
    });
  }

  initSettingsModal() {
    this.settingsModal = new SettingsModal({
      onSettingsChanged: (opts) => {
        if (opts?.gatewayUrl !== undefined) {
          this.initModelSelector();
        }
      },
      onLockApp: () => {
        this.lockScreen?.show();
      },
      onClearHistory: () => {
        this.chatView.loadHistory([]);
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

  async handleUserPrompt(promptText) {
    // Abort any prior streaming session
    this.stopGenerating();

    this.activeAbortController = new AbortController();
    this.promptInput.setStreaming(true);

    // Record t_start when prompt is submitted
    const t_start = performance.now();

    // 1. Add user message
    this.chatView.addUserMessage(promptText);

    // 2. Prepare payload with sliding window
    const messages = this.chatView.messages;
    const model = AppState.getModel();
    const gatewayBase = AppState.getGatewayUrl();
    const streamUrl = `${gatewayBase}/api/chat/stream`;

    try {
      const response = await fetchWithAuth(streamUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          messages: messages.slice(-10),
          model: model
        }),
        signal: this.activeAbortController.signal
      });

      if (!response.ok) {
        throw new Error(`Gateway returned HTTP ${response.status}`);
      }

      const t_handshake = performance.now();
      const network_ms = Math.max(1, Math.round(t_handshake - t_start));

      // Initialize assistant stream bubble
      this.chatView.startAssistantMessage();
      if (this.chatView.currentMetrics) {
        this.chatView.currentMetrics.t_start = t_start;
        this.chatView.currentMetrics.network_ms = network_ms;
      }

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop(); // keep remainder

        for (const block of blocks) {
          if (!block.trim()) continue;

          let eventType = 'message';
          let dataStr = '';

          const lines = block.split('\n');
          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              dataStr += (dataStr ? '\n' : '') + line.slice(5).trim();
            }
          }

          if (dataStr) {
            try {
              const data = JSON.parse(dataStr);
              if (eventType === 'metrics' || data.type === 'metrics') {
                this.chatView.handleMetricsEvent(data);
              } else {
                this.handleSSEEvent(data);
              }
            } catch (e) {
              console.warn('Failed to parse SSE block', block, e);
            }
          }
        }
      }

    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('Stream aborted by user');
      } else {
        this.chatView.showErrorCard(err.message || 'Network error connecting to Gateway. Please retry.');
      }
    } finally {
      this.chatView.hideToolStatus();
      const updatedMessages = this.chatView.finishAssistantMessage();
      AppState.saveHistory(updatedMessages);
      this.promptInput.setStreaming(false);
      this.activeAbortController = null;
    }
  }

  handleSSEEvent(data) {
    if (data.type === 'token') {
      this.chatView.appendToken(data.content);
    } else if (data.type === 'tool_ui') {
      this.chatView.addToolUiEvent(data);
    } else if (data.type === 'tool_start') {
      this.chatView.showToolStatus(data.name, data.args);
    } else if (data.type === 'tool_end') {
      this.chatView.hideToolStatus();
    } else if (data.type === 'metrics') {
      this.chatView.handleMetricsEvent(data);
    } else if (data.type === 'error') {
      this.chatView.hideToolStatus();
      this.chatView.showErrorCard(data.message);
    }
  }

  stopGenerating() {
    if (this.activeAbortController) {
      this.activeAbortController.abort();
      this.activeAbortController = null;
    }
    this.promptInput?.setStreaming(false);
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
