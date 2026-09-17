export class GreenModal {
  constructor(flagLabel) {
    this.flagLabel = flagLabel;
    this.modal = document.getElementById("green-modal");
    this.greenImage = document.getElementById("green-image");
    this.flagOverlay = document.getElementById("flag-overlay");
    this.flagIndicator = document.getElementById("flag-indicator");
    this.currentHole = null;
    this.flagIndex = 0;

    this.modal.querySelector(".modal-close").addEventListener("click", () => this.close());
    this.modal.addEventListener("click", (event) => {
      if (event.target === this.modal) this.close();
    });
    this.modal.addEventListener("close", () => { this.currentHole = null; });
  }

  get isOpen() {
    return this.modal.open;
  }

  open(hole, zoomLevel) {
    if (!hole?.green_image || !hole.flag_images?.length) return;
    this.currentHole = hole;
    this.flagIndex = 0;
    this.greenImage.src = hole.green_image;
    this.applyZoom(zoomLevel);
    this.updateFlag();
    this.modal.showModal();
  }

  close() {
    if (this.modal.open) this.modal.close();
  }

  nextFlag() {
    if (!this.currentHole) return;
    this.flagIndex = (this.flagIndex + 1) % this.currentHole.flag_images.length;
    this.updateFlag();
  }

  previousFlag() {
    if (!this.currentHole) return;
    const total = this.currentHole.flag_images.length;
    this.flagIndex = (this.flagIndex + total - 1) % total;
    this.updateFlag();
  }

  updateFlag() {
    const images = this.currentHole.flag_images;
    this.flagOverlay.src = images[this.flagIndex];
    this.flagIndicator.textContent = this.flagLabel(this.flagIndex + 1, images.length);
  }

  applyZoom(zoomLevel) {
    const size = 192 * zoomLevel;
    for (const image of [this.greenImage, this.flagOverlay]) {
      image.style.width = `${size}px`;
      image.style.height = `${size}px`;
    }
  }
}
