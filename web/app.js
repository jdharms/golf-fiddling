/**
 * Main Application
 *
 * Entry point for the NES Open Tournament Golf distance measurement web app.
 * Initializes components and handles user interaction.
 */

import { MeasurementState } from './measure.js';
import { OverlayRenderer } from './renderer.js';
import { UIController } from './ui.js';

let metadata = null;
let state = null;
let renderer = null;
let ui = null;

/**
 * Initialize the application
 */
async function init() {
  try {
    // Load metadata
    const response = await fetch('metadata.json');
    if (!response.ok) {
      throw new Error('Failed to load metadata.json');
    }
    metadata = await response.json();

    // Initialize components
    state = new MeasurementState();
    renderer = new OverlayRenderer(document.getElementById('overlay-canvas'));
    ui = new UIController(metadata, state, renderer);

    // Set up event listeners
    setupEventListeners();

    // Load first hole (Japan, Hole 1)
    ui.loadHole('japan', 1);

    console.log('✓ App initialized successfully');
  } catch (error) {
    console.error('Failed to initialize app:', error);
    alert('Failed to load the application. Please check the console for details.');
  }
}

/**
 * Set up event listeners for user interaction
 */
function setupEventListeners() {
  const container = document.querySelector('.image-container');

  // Left-click: Add measurement waypoint
  container.addEventListener('click', (e) => {
    if (e.target.id === 'hole-image') {
      handleClick(e);
    }
  });

  // Right-click: Clear all waypoints
  container.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    if (e.target.id === 'hole-image') {
      handleRightClick();
    }
  });
}

/**
 * Handle left-click to add waypoint
 */
function handleClick(e) {
  const img = document.getElementById('hole-image');
  const rect = img.getBoundingClientRect();

  // Get click position relative to image
  const displayX = e.clientX - rect.left;
  const displayY = e.clientY - rect.top;

  // Convert to game pixels
  // CRITICAL: (displayX / displayWidth) × imageWidth = gamePixelX
  const currentHole = ui.getCurrentHole();
  if (!currentHole) return;

  const gameX = (displayX / rect.width) * currentHole.width;
  const gameY = (displayY / rect.height) * currentHole.height;

  // Add point to measurement state
  state.addPoint(gameX, gameY);

  // Update display
  ui.updateDisplay();
}

/**
 * Handle right-click to clear all waypoints
 */
function handleRightClick() {
  state.clearPoints();
  ui.updateDisplay();
}

// Start the application when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
