import { AppState } from './state.js';
import { TabManager } from './tabs/tab_manager.js';
import { ChatView } from './tabs/chat_view.js';
import { PromptInput } from './components/prompt_input.js';
import { Lightbox } from './components/lightbox.js';
import { LockScreen } from './components/lock_screen.js';

const AVAILABLE_MODELS = [
  { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash' },
  { id: 'gemini-3.7-flash', name: 'Gemini 3.7 Flash' },
  { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash Preview' },
  { id: 'gemini-3.1-flash-lite', name: 'Gemini 3.1 Flash Lite' }
];

class App {
  constructor() {
    this.chatView = new ChatView();
    this.lightbox = new Lightbox();
    window.quantLightbox = this.lightbox;

    this.activeAbortController = null;
    this.tabManager = null;
    this.promptInput = null;
    this.lockScreen = null;

    this.init();
  }

  async init() {
    this.initTabs();
    this.initLockScreen();
    this.initSettingsModal();
    this.initPromptBar();
    this.registerServiceWorker();

    // Check 6-hour session authentication
    const isAuthenticated = await this.lockScreen.checkAuthentication();
    if (isAuthenticated) {
      this.onUnlocked();
    }
  }

  initLockScreen() {
    this.lockScreen = new LockScreen(() => this.onUnlocked());
  }

  onUnlocked() {
    this.initModelSelector();

    // Load initial chat history
    const history = AppState.getHistory();
    this.chatView.loadHistory(history);
  }

  initTabs() {
    const tabBar = document.getElementById('tabBar');
    const tabContent = document.getElementById('tabContent');
    this.tabManager = new TabManager(tabBar, tabContent);

    // Register primary Chat tab
    this.tabManager.registerTab({
      id: 'chat',
      title: 'Chat Stream',
      iconSvg: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`,
      render: (container) => this.chatView.render(container)
    });

    const activeTab = AppState.getActiveTab();
    this.tabManager.switchTab(activeTab);
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

    // Dynamically load available models from Gateway using session token
    try {
      const gatewayBase = AppState.getGatewayUrl() || '';
      const token = AppState.getSessionToken();
      const res = await fetch(`${gatewayBase}/api/models`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
      });
      if (res.ok) {
        const data = await res.json();
        if (data.models && Array.isArray(data.models)) {
          models = data.models;
        }
      } else if (res.status === 401) {
        this.handleUnauthorized('Session expired. Please unlock the app again.');
        return;
      }
    } catch (e) {
      console.warn('Using fallback models list:', e);
    }

    const currentModel = AppState.getModel();
    modelSelect.innerHTML = models.map(m =>
      `<option value="${m.id}" ${m.id === currentModel ? 'selected' : ''}>${m.name}</option>`
    ).join('');

    // If current model is not in list, default to gemini-3.5-flash
    if (!models.some(m => m.id === currentModel)) {
      AppState.setModel('gemini-3.5-flash');
      modelSelect.value = 'gemini-3.5-flash';
    } else {
      modelSelect.value = currentModel;
    }

    modelSelect.addEventListener('change', (e) => {
      AppState.setModel(e.target.value);
    });
  }

  initSettingsModal() {
    const settingsModal = document.getElementById('settingsModal');
    const settingsBtn = document.getElementById('settingsBtn');
    const closeBtn = document.getElementById('settingsClose');
    const saveBtn = document.getElementById('settingsSave');
    const clearHistoryBtn = document.getElementById('clearHistoryBtn');
    const lockAppBtn = document.getElementById('lockAppBtn');
    const passcodeInput = document.getElementById('passcodeInput');
    const gatewayUrlInput = document.getElementById('gatewayUrlInput');

    if (!settingsModal) return;

    settingsBtn?.addEventListener('click', () => {
      passcodeInput.value = '';
      passcodeInput.placeholder = AppState.getSessionToken() ? '•••••••• (Session Active)' : 'Enter passcode to log in';
      gatewayUrlInput.value = AppState.getGatewayUrl();
      settingsModal.classList.add('open');
    });

    closeBtn?.addEventListener('click', () => {
      settingsModal.classList.remove('open');
    });

    saveBtn?.addEventListener('click', async () => {
      const newGatewayUrl = gatewayUrlInput.value;
      AppState.setGatewayUrl(newGatewayUrl);

      // If user typed a new password in settings, log in and get fresh session
      const newPassword = passcodeInput.value?.trim();
      if (newPassword) {
        try {
          const res = await fetch(`${newGatewayUrl}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: newPassword })
          });
          if (res.ok) {
            const data = await res.json();
            AppState.setSessionToken(data.token, data.expires_at);
          } else {
            alert('Invalid passcode. Session was not updated.');
          }
        } catch (err) {
          console.warn('Failed to update session from settings:', err);
        }
      }

      settingsModal.classList.remove('open');
      this.initModelSelector();
    });

    lockAppBtn?.addEventListener('click', () => {
      AppState.clearSession();
      settingsModal.classList.remove('open');
      this.lockScreen.show();
    });

    clearHistoryBtn?.addEventListener('click', () => {
      if (confirm('Clear all conversation history?')) {
        AppState.clearHistory();
        this.chatView.loadHistory([]);
        settingsModal.classList.remove('open');
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

    // 1. Add user message
    this.chatView.addUserMessage(promptText);

    // 2. Prepare payload with sliding window
    const messages = this.chatView.messages;
    const model = AppState.getModel();
    const token = AppState.getSessionToken();
    const gatewayBase = AppState.getGatewayUrl();
    const streamUrl = `${gatewayBase}/api/chat/stream`;

    try {
      const response = await fetch(streamUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          messages: messages,
          model: model
        }),
        signal: this.activeAbortController.signal
      });

      if (!response.ok) {
        if (response.status === 401) {
          this.handleUnauthorized('Session expired. Please unlock the app again.');
          return;
        }
        throw new Error(`Gateway returned HTTP ${response.status}`);
      }

      // Initialize assistant stream bubble
      this.chatView.startAssistantMessage();

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop(); // keep remainder

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              this.handleSSEEvent(data);
            } catch (e) {
              console.warn('Failed to parse SSE line', line, e);
            }
          }
        }
      }

    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('Stream aborted by user');
      } else {
        this.chatView.startAssistantMessage();
        this.chatView.appendToken(`⚠️ **Error:** ${err.message}`);
      }
    } finally {
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
    } else if (data.type === 'error') {
      this.chatView.appendToken(`\n\n⚠️ **Service Error:** ${data.message}\n\n`);
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
        navigator.serviceWorker.register('./sw.js').catch((err) => {
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
