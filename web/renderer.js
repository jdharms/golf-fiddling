/**
 * Canvas Overlay Renderer
 *
 * Renders measurement lines, waypoint circles, and distance labels on a canvas overlay.
 * Visual style matches editor/rendering/terrain_renderer.py:327-409
 */

export class OverlayRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');

    // Colors matching editor
    this.lineColor = '#00FFFF';    // Cyan
    this.pointColor = '#FFFF00';   // Yellow
    this.textColor = '#FFFFFF';    // White
    this.bgColor = '#000000';      // Black
  }

  /**
   * Render measurement overlay on canvas
   *
   * @param {MeasurementState} state - Current measurement state
   * @param {number} imageWidth - Original image width in pixels
   * @param {number} imageHeight - Original image height in pixels
   */
  render(state, imageWidth, imageHeight) {
    // Clear canvas
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    if (state.points.length === 0) {
      return;
    }

    // Convert game pixels to display coordinates
    const displayPoints = state.points.map(p =>
      this._gamePixelToDisplay(p, imageWidth, imageHeight)
    );

    // Draw lines between consecutive points
    const segments = state.getSegmentDistances();
    for (let i = 0; i < displayPoints.length - 1; i++) {
      const p1 = displayPoints[i];
      const p2 = displayPoints[i + 1];

      // Draw line
      this.ctx.strokeStyle = this.lineColor;
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.stroke();

      // Draw distance label at midpoint
      const midX = (p1.x + p2.x) / 2;
      const midY = (p1.y + p2.y) / 2;
      const distance = segments[i];
      this._drawLabel(midX, midY, `${distance.toFixed(1)}y`);
    }

    // Draw points (on top of lines)
    for (const p of displayPoints) {
      // Yellow filled circle
      this.ctx.fillStyle = this.pointColor;
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, 4, 0, 2 * Math.PI);
      this.ctx.fill();

      // Black outline
      this.ctx.strokeStyle = '#000000';
      this.ctx.lineWidth = 1;
      this.ctx.stroke();
    }
  }

  /**
   * Draw a distance label with background
   */
  _drawLabel(x, y, text) {
    this.ctx.font = '12px monospace';
    const metrics = this.ctx.measureText(text);

    // Calculate background rectangle size
    const padding = 2;
    const width = metrics.width + padding * 2;
    const height = 14;

    // Draw black background
    this.ctx.fillStyle = this.bgColor;
    this.ctx.fillRect(
      x - width / 2,
      y - height / 2,
      width,
      height
    );

    // Draw cyan border
    this.ctx.strokeStyle = this.lineColor;
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(
      x - width / 2,
      y - height / 2,
      width,
      height
    );

    // Draw white text
    this.ctx.fillStyle = this.textColor;
    this.ctx.textAlign = 'center';
    this.ctx.textBaseline = 'middle';
    this.ctx.fillText(text, x, y);
  }

  /**
   * Convert game pixel coordinates to display canvas coordinates
   */
  _gamePixelToDisplay(gamePixel, imageWidth, imageHeight) {
    const displayWidth = this.canvas.width;
    const displayHeight = this.canvas.height;

    return {
      x: (gamePixel.x / imageWidth) * displayWidth,
      y: (gamePixel.y / imageHeight) * displayHeight
    };
  }

  /**
   * Resize canvas to match displayed image dimensions
   * CRITICAL: Canvas internal dimensions must match display dimensions
   */
  resize(displayWidth, displayHeight) {
    this.canvas.width = displayWidth;
    this.canvas.height = displayHeight;
  }
}
