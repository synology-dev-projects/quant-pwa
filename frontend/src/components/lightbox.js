export class Lightbox {
  constructor() {
    this.overlay = document.getElementById('lightboxModal');
    this.image = document.getElementById('lightboxImage');
    this.closeBtn = document.getElementById('lightboxClose');
    
    this.scale = 1;
    this.panning = false;
    this.pointX = 0;
    this.pointY = 0;
    this.startX = 0;
    this.startY = 0;

    this.initEvents();
  }

  initEvents() {
    if (!this.overlay) return;

    this.closeBtn?.addEventListener('click', () => this.close());
    
    // Close on backdrop tap
    this.overlay.addEventListener('click', (e) => {
      if (e.target === this.overlay || e.target.classList.contains('lightbox-content')) {
        this.close();
      }
    });

    // Double tap to toggle zoom on mobile
    let lastTap = 0;
    this.image?.addEventListener('touchend', (e) => {
      const currentTime = new Date().getTime();
      const tapLength = currentTime - lastTap;
      if (tapLength < 300 && tapLength > 0) {
        this.toggleZoom(e);
        e.preventDefault();
      }
      lastTap = currentTime;
    });
  }

  open(src, alt = 'Options Chart') {
    if (!this.overlay || !this.image) return;
    this.image.src = src;
    this.image.alt = alt;
    this.scale = 1;
    this.updateTransform();
    this.overlay.classList.add('open');
  }

  close() {
    if (!this.overlay) return;
    this.overlay.classList.remove('open');
    if (this.image) {
      this.image.src = '';
    }
  }

  toggleZoom(e) {
    if (this.scale > 1) {
      this.scale = 1;
      this.pointX = 0;
      this.pointY = 0;
    } else {
      this.scale = 2.2;
    }
    this.updateTransform();
  }

  updateTransform() {
    if (this.image) {
      this.image.style.transform = `scale(${this.scale})`;
    }
  }
}
