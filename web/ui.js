/**
 * UI Controller
 *
 * Manages UI components, course/hole selection, and display updates.
 */

export class UIController {
  constructor(metadata, state, renderer) {
    this.metadata = metadata;
    this.state = state;
    this.renderer = renderer;

    // DOM elements
    this.courseSelect = document.getElementById('course-select');
    this.holeSelect = document.getElementById('hole-select');
    this.holeInfo = document.getElementById('hole-info');
    this.distanceDisplay = document.getElementById('distance-display');
    this.holeImage = document.getElementById('hole-image');
    this.overlayCanvas = document.getElementById('overlay-canvas');

    // Zoom controls
    this.zoomLevel = 2;  // Default to 2x for better visibility on modern displays
    this.minZoom = 1;
    this.maxZoom = 8;

    // Current hole data
    this.currentHole = null;

    // Initialize UI
    this._initializeUI();
  }

  /**
   * Initialize UI components and event listeners
   */
  _initializeUI() {
    // Populate course selector
    for (const courseId in this.metadata.courses) {
      const course = this.metadata.courses[courseId];
      const option = document.createElement('option');
      option.value = courseId;
      option.textContent = course.name;
      this.courseSelect.appendChild(option);
    }

    // Course selection change handler
    this.courseSelect.addEventListener('change', () => {
      this.selectCourse(this.courseSelect.value);
    });

    // Hole selection change handler
    this.holeSelect.addEventListener('change', () => {
      this.selectHole(parseInt(this.holeSelect.value));
    });

    // Zoom button handlers
    document.getElementById('zoom-in').addEventListener('click', () => {
      this.zoomIn();
    });

    document.getElementById('zoom-out').addEventListener('click', () => {
      this.zoomOut();
    });

    document.getElementById('zoom-reset').addEventListener('click', () => {
      this.setZoom(2);  // Reset to 2x
    });

    // Image load handler
    this.holeImage.addEventListener('load', () => {
      this.resizeCanvas();
    });

    // Window resize handler
    window.addEventListener('resize', () => {
      this.resizeCanvas();
    });

    // Update zoom display
    this._updateZoomDisplay();
  }

  /**
   * Load a specific course and hole
   */
  loadHole(courseId, holeNumber) {
    // Clear measurements when switching holes
    this.state.clearPoints();
    this.state.setLocation(courseId, holeNumber);

    // Update selectors
    this.courseSelect.value = courseId;
    this._populateHoleSelector(courseId);
    this.holeSelect.value = holeNumber;

    // Load hole data
    const course = this.metadata.courses[courseId];
    this.currentHole = course.holes.find(h => h.number === holeNumber);

    if (!this.currentHole) {
      console.error(`Hole ${holeNumber} not found in ${courseId}`);
      return;
    }

    // Update image
    this.holeImage.src = this.currentHole.image;

    // Update hole info display
    this._updateHoleInfo();

    // Update distance display
    this.updateDisplay();
  }

  /**
   * Select a course
   */
  selectCourse(courseId) {
    this._populateHoleSelector(courseId);
    this.loadHole(courseId, 1);
  }

  /**
   * Select a hole in the current course
   */
  selectHole(holeNumber) {
    this.loadHole(this.state.courseId, holeNumber);
  }

  /**
   * Populate hole selector dropdown for a course
   */
  _populateHoleSelector(courseId) {
    // Clear existing options
    this.holeSelect.innerHTML = '';

    const course = this.metadata.courses[courseId];
    for (const hole of course.holes) {
      const option = document.createElement('option');
      option.value = hole.number;
      option.textContent = `Hole ${hole.number}`;
      this.holeSelect.appendChild(option);
    }
  }

  /**
   * Update hole info display (par, distance)
   */
  _updateHoleInfo() {
    if (!this.currentHole) return;
    this.holeInfo.textContent = `Par ${this.currentHole.par} • ${this.currentHole.distance}y`;
  }

  /**
   * Update distance display and re-render overlay
   */
  updateDisplay() {
    const totalDistance = this.state.calculateTotalDistance();
    const pointCount = this.state.getPointCount();

    if (pointCount === 0) {
      this.distanceDisplay.textContent = 'Distance: 0.0y';
    } else if (pointCount === 1) {
      this.distanceDisplay.textContent = '1 point';
    } else {
      this.distanceDisplay.textContent = `Distance: ${totalDistance.toFixed(1)}y`;
    }

    // Re-render overlay
    if (this.currentHole) {
      this.renderer.render(
        this.state,
        this.currentHole.width,
        this.currentHole.height
      );
    }
  }

  /**
   * Resize canvas to match displayed image dimensions
   * CRITICAL: Must be called when image loads or window resizes or zoom changes
   */
  resizeCanvas() {
    if (!this.currentHole) return;

    // Apply integer scaling to image
    const scaledWidth = this.currentHole.width * this.zoomLevel;
    const scaledHeight = this.currentHole.height * this.zoomLevel;

    this.holeImage.style.width = `${scaledWidth}px`;
    this.holeImage.style.height = `${scaledHeight}px`;

    // Match canvas size to scaled image
    this.overlayCanvas.width = scaledWidth;
    this.overlayCanvas.height = scaledHeight;
    this.overlayCanvas.style.width = `${scaledWidth}px`;
    this.overlayCanvas.style.height = `${scaledHeight}px`;

    // Resize renderer
    this.renderer.resize(scaledWidth, scaledHeight);

    // Re-render measurements at new size
    this.renderer.render(
      this.state,
      this.currentHole.width,
      this.currentHole.height
    );
  }

  /**
   * Set zoom level (integer only)
   */
  setZoom(level) {
    level = Math.max(this.minZoom, Math.min(this.maxZoom, Math.floor(level)));
    this.zoomLevel = level;
    this._updateZoomDisplay();
    this.resizeCanvas();
  }

  /**
   * Zoom in by 1x
   */
  zoomIn() {
    if (this.zoomLevel < this.maxZoom) {
      this.setZoom(this.zoomLevel + 1);
    }
  }

  /**
   * Zoom out by 1x
   */
  zoomOut() {
    if (this.zoomLevel > this.minZoom) {
      this.setZoom(this.zoomLevel - 1);
    }
  }

  /**
   * Update zoom display text and button states
   */
  _updateZoomDisplay() {
    const zoomDisplay = document.getElementById('zoom-display');
    if (zoomDisplay) {
      zoomDisplay.textContent = `${this.zoomLevel}x`;
    }

    // Update button states
    const zoomInBtn = document.getElementById('zoom-in');
    const zoomOutBtn = document.getElementById('zoom-out');

    if (zoomInBtn) {
      zoomInBtn.disabled = this.zoomLevel >= this.maxZoom;
    }

    if (zoomOutBtn) {
      zoomOutBtn.disabled = this.zoomLevel <= this.minZoom;
    }
  }

  /**
   * Get current hole data
   */
  getCurrentHole() {
    return this.currentHole;
  }
}
