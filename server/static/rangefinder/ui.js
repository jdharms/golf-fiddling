export class UIController {
  constructor(metadata, state, renderer, text) {
    this.metadata = metadata;
    this.state = state;
    this.renderer = renderer;
    this.text = text;
    this.courseSelect = document.getElementById("course-select");
    this.holeSelect = document.getElementById("hole-select");
    this.holeInfo = document.getElementById("hole-info");
    this.distanceDisplay = document.getElementById("distance-display");
    this.viewer = document.querySelector(".rangefinder-viewer");
    this.holeImage = document.getElementById("hole-image");
    this.overlayCanvas = document.getElementById("overlay-canvas");
    this.zoomLevel = 2;
    this.minZoom = 1;
    this.maxZoom = 8;
    this.currentHole = null;
    this.initialize();
  }

  initialize() {
    const groups = new Map();
    for (const [courseId, course] of Object.entries(this.metadata.courses)) {
      const option = document.createElement("option");
      option.value = courseId;
      option.textContent = course.name;
      let parent = this.courseSelect;
      if (course.group) {
        if (!groups.has(course.group)) {
          const group = document.createElement("optgroup");
          group.label = course.group;
          this.courseSelect.appendChild(group);
          groups.set(course.group, group);
        }
        parent = groups.get(course.group);
      }
      parent.appendChild(option);
    }

    this.courseSelect.addEventListener("change", () => this.loadHole(this.courseSelect.value, 1));
    this.holeSelect.addEventListener("change", () => this.loadHole(this.state.courseId, Number(this.holeSelect.value)));
    document.getElementById("zoom-in").addEventListener("click", () => this.setZoom(this.zoomLevel + 1));
    document.getElementById("zoom-out").addEventListener("click", () => this.setZoom(this.zoomLevel - 1));
    document.getElementById("zoom-reset").addEventListener("click", () => this.setZoom(2));
    document.getElementById("clear-waypoints").addEventListener("click", () => {
      this.state.clearPoints();
      this.updateDisplay();
    });
    this.holeImage.addEventListener("load", () => {
      this.resizeCanvas();
      this.viewer.scrollTop = this.viewer.scrollHeight;
    });
    this.updateZoomDisplay();
  }

  loadHole(courseId, holeNumber) {
    this.state.clearPoints();
    this.state.clearPreviewPoint();
    this.state.setLocation(courseId, holeNumber);
    this.courseSelect.value = courseId;
    this.populateHoles(courseId);
    this.holeSelect.value = String(holeNumber);
    const course = this.metadata.courses[courseId];
    this.currentHole = course.holes.find((hole) => hole.number === holeNumber);
    if (!this.currentHole) return;
    this.holeImage.src = this.currentHole.image;
    this.holeInfo.textContent = this.text.holeInfo(this.currentHole.par, this.currentHole.distance);
    this.updateDisplay();
  }

  populateHoles(courseId) {
    this.holeSelect.replaceChildren();
    for (const hole of this.metadata.courses[courseId].holes) {
      const option = document.createElement("option");
      option.value = String(hole.number);
      option.textContent = this.text.holeOption(hole.number);
      this.holeSelect.appendChild(option);
    }
  }

  updateDisplay() {
    const distance = this.state.calculateTotalDistance();
    this.distanceDisplay.textContent = this.state.getPointCount() < 2
      ? this.text.distanceEmpty()
      : this.text.distance(distance);
    if (this.currentHole) this.renderer.render(this.state, this.currentHole.width, this.currentHole.height);
  }

  resizeCanvas() {
    if (!this.currentHole) return;
    const width = this.currentHole.width * this.zoomLevel;
    const height = this.currentHole.height * this.zoomLevel;
    this.holeImage.style.width = `${width}px`;
    this.holeImage.style.height = `${height}px`;
    this.overlayCanvas.style.width = `${width}px`;
    this.overlayCanvas.style.height = `${height}px`;
    this.renderer.resize(width, height);
    this.renderer.render(this.state, this.currentHole.width, this.currentHole.height);
  }

  setZoom(level) {
    this.zoomLevel = Math.max(this.minZoom, Math.min(this.maxZoom, Math.floor(level)));
    this.updateZoomDisplay();
    this.resizeCanvas();
  }

  updateZoomDisplay() {
    document.getElementById("zoom-display").textContent = this.text.zoom(this.zoomLevel);
    document.getElementById("zoom-in").disabled = this.zoomLevel >= this.maxZoom;
    document.getElementById("zoom-out").disabled = this.zoomLevel <= this.minZoom;
  }

  previousHole() {
    if (this.state.holeNumber > 1) this.loadHole(this.state.courseId, this.state.holeNumber - 1);
  }

  nextHole() {
    const holes = this.metadata.courses[this.state.courseId].holes;
    if (this.state.holeNumber < holes.length) this.loadHole(this.state.courseId, this.state.holeNumber + 1);
  }

  updatePreview(x, y) {
    this.state.setPreviewPoint(x, y);
    this.renderer.render(this.state, this.currentHole.width, this.currentHole.height);
  }

  clearPreview() {
    this.state.clearPreviewPoint();
    if (this.currentHole) this.renderer.render(this.state, this.currentHole.width, this.currentHole.height);
  }
}
