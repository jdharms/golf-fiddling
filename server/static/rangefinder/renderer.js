export class OverlayRenderer {
  constructor(canvas, segmentLabel) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.segmentLabel = segmentLabel;
    this.lineColor = "#00ffff";
    this.pointColor = "#ffff00";
    this.previewColor = "#ffa500";
  }

  render(state, imageWidth, imageHeight) {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (state.points.length === 0) return;

    const points = state.points.map((point) =>
      this.toDisplay(point, imageWidth, imageHeight),
    );
    const segments = state.getSegmentDistances();
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      this.drawLine(start, end, this.lineColor);
      this.drawLabel(
        (start.x + end.x) / 2,
        (start.y + end.y) / 2,
        this.segmentLabel(segments[index]),
        this.lineColor,
      );
    }

    if (state.previewPoint && points.length > 0) {
      const start = points.at(-1);
      const end = this.toDisplay(state.previewPoint, imageWidth, imageHeight);
      this.drawLine(start, end, this.previewColor, [8, 8]);
      this.drawLabel(
        (start.x + end.x) / 2,
        (start.y + end.y) / 2,
        this.segmentLabel(state.getPreviewDistance()),
        this.previewColor,
      );
    }

    for (const point of points) {
      this.ctx.fillStyle = this.pointColor;
      this.ctx.beginPath();
      this.ctx.arc(point.x, point.y, 4, 0, 2 * Math.PI);
      this.ctx.fill();
      this.ctx.strokeStyle = "#000000";
      this.ctx.lineWidth = 1;
      this.ctx.stroke();
    }
  }

  drawLine(start, end, color, dash = []) {
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 2;
    this.ctx.setLineDash(dash);
    this.ctx.beginPath();
    this.ctx.moveTo(start.x, start.y);
    this.ctx.lineTo(end.x, end.y);
    this.ctx.stroke();
    this.ctx.setLineDash([]);
  }

  drawLabel(x, y, text, color) {
    this.ctx.font = "12px monospace";
    const width = this.ctx.measureText(text).width + 4;
    this.ctx.fillStyle = "#000000";
    this.ctx.fillRect(x - width / 2, y - 7, width, 14);
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(x - width / 2, y - 7, width, 14);
    this.ctx.fillStyle = "#ffffff";
    this.ctx.textAlign = "center";
    this.ctx.textBaseline = "middle";
    this.ctx.fillText(text, x, y);
  }

  toDisplay(point, imageWidth, imageHeight) {
    return {
      x: (point.x / imageWidth) * this.canvas.width,
      y: (point.y / imageHeight) * this.canvas.height,
    };
  }

  resize(width, height) {
    this.canvas.width = width;
    this.canvas.height = height;
  }
}
