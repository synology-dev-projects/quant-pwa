const STORAGE_KEYS = {
  PASSCODE: 'quant_app_passcode',
  MODEL: 'quant_selected_model',
  GATEWAY_URL: 'quant_gateway_url',
  ACTIVE_TAB: 'quant_active_tab',
  CHAT_HISTORY: 'quant_chat_history'
};

export const AppState = {
  getPasscode() {
    return localStorage.getItem(STORAGE_KEYS.PASSCODE) || 'quant-secret-2026';
  },

  setPasscode(passcode) {
    localStorage.setItem(STORAGE_KEYS.PASSCODE, passcode.trim());
  },

  getModel() {
    return localStorage.getItem(STORAGE_KEYS.MODEL) || 'gemini-3.7-flash';
  },

  setModel(modelId) {
    localStorage.setItem(STORAGE_KEYS.MODEL, modelId);
  },

  getGatewayUrl() {
    // Defaults to relative URL (works seamlessly via Cloudflare Tunnel or reverse proxy)
    return localStorage.getItem(STORAGE_KEYS.GATEWAY_URL) || '';
  },

  setGatewayUrl(url) {
    localStorage.setItem(STORAGE_KEYS.GATEWAY_URL, url.trim().replace(/\/$/, ''));
  },

  getActiveTab() {
    return localStorage.getItem(STORAGE_KEYS.ACTIVE_TAB) || 'chat';
  },

  setActiveTab(tabId) {
    localStorage.setItem(STORAGE_KEYS.ACTIVE_TAB, tabId);
  },

  getHistory() {
    try {
      const data = localStorage.getItem(STORAGE_KEYS.CHAT_HISTORY);
      return data ? JSON.parse(data) : [];
    } catch (e) {
      console.warn('Failed to parse chat history from localStorage', e);
      return [];
    }
  },

  saveHistory(messages) {
    try {
      localStorage.setItem(STORAGE_KEYS.CHAT_HISTORY, JSON.stringify(messages));
    } catch (e) {
      console.warn('Failed to save chat history to localStorage', e);
    }
  },

  clearHistory() {
    localStorage.removeItem(STORAGE_KEYS.CHAT_HISTORY);
  }
};
