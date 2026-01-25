/**
 * Green Modal
 *
 * Modal dialog showing detailed green view with flag position overlays.
 */

export class GreenModal {
  constructor() {
    // DOM elements
    this.modal = document.getElementById('green-modal');
    this.backdrop = this.modal.querySelector('.modal-backdrop');
    this.closeButton = this.modal.querySelector('.modal-close');
    this.greenImage = document.getElementById('green-image');
    this.flagOverlay = document.getElementById('flag-overlay');
    this.flagIndicator = document.getElementById('flag-indicator');

    // State
    this.isOpen = false;
    this.currentHole = null;
    this.flagIndex = 0;
    this.zoomLevel = 2;

    // Bind event handlers
    this._bindEvents();
  }

  /**
   * Bind event handlers for modal interaction
   */
  _bindEvents() {
    // Close on backdrop click
    this.backdrop.addEventListener('click', () => {
      this.close();
    });

    // Close button
    this.closeButton.addEventListener('click', () => {
      this.close();
    });
  }

  /**
   * Open the modal with the specified hole data
   * @param {Object} hole - Hole metadata object
   * @param {number} zoomLevel - Current zoom level
   */
  open(hole, zoomLevel) {
    if (!hole || !hole.green_image || !hole.flag_images) {
      console.warn('Hole data missing green_image or flag_images');
      return;
    }

    this.currentHole = hole;
    this.zoomLevel = zoomLevel;
    this.flagIndex = 0;

    // Load images
    this.greenImage.src = hole.green_image;
    this._updateFlagOverlay();

    // Apply zoom scaling (greens are 192x192 at 1x)
    this._applyZoom();

    // Show modal
    this.modal.classList.remove('hidden');
    this.isOpen = true;
  }

  /**
   * Close the modal
   */
  close() {
    this.modal.classList.add('hidden');
    this.isOpen = false;
    this.currentHole = null;
  }

  /**
   * Navigate to the next flag position
   */
  nextFlag() {
    if (!this.currentHole) return;

    this.flagIndex = (this.flagIndex + 1) % 4;
    this._updateFlagOverlay();
  }

  /**
   * Navigate to the previous flag position
   */
  previousFlag() {
    if (!this.currentHole) return;

    this.flagIndex = (this.flagIndex + 3) % 4;  // +3 mod 4 == -1 mod 4
    this._updateFlagOverlay();
  }

  /**
   * Update zoom level while modal is open
   * @param {number} zoomLevel - New zoom level
   */
  updateZoom(zoomLevel) {
    this.zoomLevel = zoomLevel;
    if (this.isOpen) {
      this._applyZoom();
    }
  }

  /**
   * Update the flag overlay image and indicator
   */
  _updateFlagOverlay() {
    if (!this.currentHole || !this.currentHole.flag_images) return;

    const flagImages = this.currentHole.flag_images;
    if (this.flagIndex < flagImages.length) {
      this.flagOverlay.src = flagImages[this.flagIndex];
    }

    // Update indicator (1-indexed for display)
    this.flagIndicator.textContent = `Flag ${this.flagIndex + 1}/4`;
  }

  /**
   * Apply zoom scaling to green images
   */
  _applyZoom() {
    // Greens are 192x192 pixels at 1x
    const baseSize = 192;
    const scaledSize = baseSize * this.zoomLevel;

    this.greenImage.style.width = `${scaledSize}px`;
    this.greenImage.style.height = `${scaledSize}px`;
    this.flagOverlay.style.width = `${scaledSize}px`;
    this.flagOverlay.style.height = `${scaledSize}px`;
  }
}
