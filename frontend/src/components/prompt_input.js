export class PromptInput {
  constructor(container, onSubmit, onStop) {
    this.container = container;
    this.onSubmit = onSubmit;
    this.onStop = onStop;
    this.isStreaming = false;

    this.render();
    this.initEvents();
  }

  render() {
    this.container.innerHTML = `
      <div class="quick-chips-bar">
        <button class="chip-btn" data-prompt="Analyze GEX and dealer positioning on SPY">/gex SPY</button>
        <button class="chip-btn" data-prompt="Analyze GEX and dealer positioning on NVDA">/gex NVDA</button>
        <button class="chip-btn" data-prompt="Analyze GEX and dealer positioning on AAPL">/gex AAPL</button>
        <button class="chip-btn" data-prompt="Analyze GEX and dealer positioning on TSLA">/gex TSLA</button>
        <button class="chip-btn" data-prompt="What are the key macro catalysts and economic releases this week?">/macro</button>
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

    this.textarea = this.container.querySelector('#promptTextarea');
    this.form = this.container.querySelector('#promptForm');
    this.sendBtn = this.container.querySelector('#sendBtn');
    this.stopBtn = this.container.querySelector('#stopBtn');
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

    // Quick chips
    this.container.querySelectorAll('.chip-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const prompt = btn.getAttribute('data-prompt');
        if (prompt) {
          this.textarea.value = prompt;
          this.submit();
        }
      });
    });
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
