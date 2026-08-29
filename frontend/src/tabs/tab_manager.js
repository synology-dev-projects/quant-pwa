export class TabManager {
  constructor(tabBarContainer, contentContainer, onTabChange = null) {
    this.tabBarContainer = tabBarContainer;
    this.contentContainer = contentContainer;
    this.onTabChange = onTabChange;
    this.tabs = new Map();
    this.activeTabId = null;
  }

  registerTab({ id, title, iconSvg, render }) {
    this.tabs.set(id, { id, title, iconSvg, render, element: null });
    this.renderTabs();
  }

  renderTabs() {
    this.tabBarContainer.innerHTML = '';
    
    this.tabs.forEach((tab) => {
      const btn = document.createElement('button');
      btn.className = `tab-btn ${tab.id === this.activeTabId ? 'active' : ''}`;
      btn.innerHTML = `${tab.iconSvg || ''} <span>${tab.title}</span>`;
      btn.addEventListener('click', () => this.switchTab(tab.id));
      this.tabBarContainer.appendChild(btn);

      // Create content pane if not created
      if (!tab.element) {
        const pane = document.createElement('div');
        pane.className = `tab-pane ${tab.id === this.activeTabId ? 'active' : ''}`;
        pane.id = `tab-${tab.id}`;
        tab.render(pane);
        tab.element = pane;
        this.contentContainer.appendChild(pane);
      }
    });
  }

  switchTab(tabId) {
    if (!this.tabs.has(tabId) || this.activeTabId === tabId) return;

    this.activeTabId = tabId;

    // Update buttons
    const buttons = this.tabBarContainer.querySelectorAll('.tab-btn');
    let idx = 0;
    this.tabs.forEach((tab) => {
      if (buttons[idx]) {
        buttons[idx].classList.toggle('active', tab.id === tabId);
      }
      if (tab.element) {
        tab.element.classList.toggle('active', tab.id === tabId);
      }
      idx++;
    });

    if (typeof this.onTabChange === 'function') {
      this.onTabChange(tabId);
    }
  }
}
