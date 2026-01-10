/**
 * Measurement State and Distance Calculation
 *
 * Manages measurement points and calculates distances in yards.
 * Distance formula: sqrt(dx² + dy²) × 2 = yards
 * (from editor/tools/measure_tool.py:37)
 */

export class MeasurementState {
  constructor() {
    this.points = [];  // Array of {x, y} in game pixels
    this.courseId = 'japan';
    this.holeNumber = 1;
  }

  /**
   * Add a measurement point in game pixel coordinates
   */
  addPoint(gamePixelX, gamePixelY) {
    this.points.push({ x: gamePixelX, y: gamePixelY });
  }

  /**
   * Clear all measurement points
   */
  clearPoints() {
    this.points = [];
  }

  /**
   * Calculate total cumulative distance through all waypoints
   * Returns distance in yards
   */
  calculateTotalDistance() {
    if (this.points.length < 2) {
      return 0;
    }

    let total = 0;
    for (let i = 0; i < this.points.length - 1; i++) {
      const p1 = this.points[i];
      const p2 = this.points[i + 1];
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      // CRITICAL: Factor of 2 converts game pixels to yards
      total += Math.sqrt(dx * dx + dy * dy) * 2;
    }

    return total;
  }

  /**
   * Get distances for each segment
   * Returns array of distances in yards
   */
  getSegmentDistances() {
    const segments = [];
    for (let i = 0; i < this.points.length - 1; i++) {
      const p1 = this.points[i];
      const p2 = this.points[i + 1];
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      // CRITICAL: Factor of 2 converts game pixels to yards
      segments.push(Math.sqrt(dx * dx + dy * dy) * 2);
    }
    return segments;
  }

  /**
   * Get number of measurement points
   */
  getPointCount() {
    return this.points.length;
  }

  /**
   * Set current course and hole
   */
  setLocation(courseId, holeNumber) {
    this.courseId = courseId;
    this.holeNumber = holeNumber;
  }
}
