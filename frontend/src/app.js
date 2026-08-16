import { AppState } from './state.js';
import { TabManager } from './tabs/tab_manager.js';
import { ChatView } from './tabs/chat_view.js';
import { PromptInput } from './components/prompt_input.js';
import { Lightbox } from './components/lightbox.js';

class App {
  constructor() {
    this.chatView = new ChatView();
    this.lightbox = new Lightbox();
    window.quantLightbox = this.lightbox;

    this.activeAbortController = null;
    this.tabManager = null;
    this.promptInput = null;

    this.init();
  }

  async init() {
    this.initTabs();
    this.initSettingsModal();
    this.initModelSelector();
    this.initPromptBar();
    this.registerServiceWorker();

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

  initModelSelector() {
    const modelSelect = document.getElementById('modelSelect');
    if (!modelSelect) return;

    modelSelect.value = AppState.getModel();
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
    const passcodeInput = document.getElementById('passcodeInput');
    const gatewayUrlInput = document.getElementById('gatewayUrlInput');

    if (!settingsModal) return;

    settingsBtn?.addEventListener('click', () => {
      passcodeInput.value = AppState.getPasscode();
      gatewayUrlInput.value = AppState.getGatewayUrl();
      settingsModal.classList.add('open');
    });

    closeBtn?.addEventListener('click', () => {
      settingsModal.classList.remove('open');
    });

    saveBtn?.addEventListener('click', () => {
      AppState.setPasscode(passcodeInput.value);
      AppState.setGatewayUrl(gatewayUrlInput.value);
      settingsModal.classList.remove('open');
    });

    clearHistoryBtn?.addEventListener('click', () => {
      if (confirm('Clear all conversation history?')) {
        AppState.clearHistory();
        this.chatView.loadHistory([]);
        settingsModal.classList.remove('open');
      }
    });
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
    const passcode = AppState.getPasscode();
    const gatewayBase = AppState.getGatewayUrl();
    const streamUrl = `${gatewayBase}/api/chat/stream`;

    try {
      const response = await fetch(streamUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${passcode}`
        },
        body: JSON.stringify({
          messages: messages,
          model: model
        }),
        signal: this.activeAbortController.signal
      });

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Invalid App Passcode. Please check Settings.');
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
