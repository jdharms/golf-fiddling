# NES Open Tournament Golf - Distance Measurement Tool

A client-side web application for measuring distances on golf course images from NES Open Tournament Golf.

## Features

- **All 54 Holes**: Browse all holes from Japan, US, and UK courses
- **Integer Zoom**: 1x-8x zoom with pixel-perfect scaling for crisp NES graphics
- **Waypoint Measurement**: Click to add multiple waypoints and measure cumulative distances
- **Accurate Calculations**: Uses the exact formula from the editor (`sqrt(dx² + dy²) × 2 = yards`)
- **Zoom-Independent Math**: Distance calculations remain accurate at all zoom levels
- **Visual Feedback**: Cyan lines, yellow waypoint markers, and distance labels
- **No Backend Required**: Pure client-side JavaScript, deployable to GitHub Pages

## Usage

### Local Testing

1. **Generate Images** (first time only):
   ```bash
   golf-render-web data/chr-ram.bin courses/ web/
   ```

2. **Start Local Server**:
   ```bash
   cd web
   python3 -m http.server 8000
   ```

3. **Open in Browser**:
   Navigate to `http://localhost:8000`

### Controls

- **Left-click**: Add a measurement waypoint
- **Right-click**: Clear all waypoints
- **Course/Hole Selector**: Switch between courses and holes
- **Zoom Controls**:
  - **+** button: Zoom in (up to 8x)
  - **−** button: Zoom out (down to 1x)
  - **Reset** button: Return to 2x (default)
  - Current zoom level displayed in cyan
  - **Note**: At high zoom levels, the image will be larger than the screen and you can scroll to see different areas
- **Distance Display**: Shows total cumulative distance in yards

### Measurement Tips

- Click on the tee position to start
- Add waypoints along your intended path
- Click on the green/flag to finish
- The total distance accounts for curves and obstacles
- Use waypoints to measure around hazards or doglegs
- **For precise measurements**: Zoom in (2x-4x), scroll to position the area of interest, then click
- **For overview**: Use 1x-2x zoom to see the entire hole at once

## Deployment to GitHub Pages

### Option 1: Simple Deployment (Recommended)

1. Create a new repository for the web app
2. Copy the `web/` directory contents to the repository root
3. Commit all files (including images and metadata.json)
4. Enable GitHub Pages in repository Settings
5. Set source to `main` branch, `/` (root) folder
6. Access at `https://username.github.io/repo-name/`

### Option 2: Automated Deployment with GitHub Actions

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [ main ]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install pillow numpy

      - name: Generate images
        run: |
          python tools/render_web.py data/chr-ram.bin courses/ web/

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./web
```

This approach keeps images out of the main repository and generates them during deployment.

## File Structure

```
web/
  index.html       - Main HTML structure
  styles.css       - UI styling
  app.js           - Main application logic
  measure.js       - Measurement state and calculations
  renderer.js      - Canvas overlay rendering
  ui.js            - UI component management
  metadata.json    - Course/hole metadata (generated)
  images/          - Pre-rendered hole images (generated)
    japan/
      hole_01.png ... hole_18.png
    us/
      hole_01.png ... hole_18.png
    uk/
      hole_01.png ... hole_18.png
```

## Technical Details

### Coordinate System

- Images rendered at 1:1 scale (8px per NES tile)
- Image pixels = game pixels (no scaling needed)
- Distance calculation: `Math.sqrt(dx² + dx²) × 2 = yards`

### Zoom System

Integer-only scaling (1x, 2x, 3x, 4x, etc.) ensures pixel-perfect rendering:
- Default: 2x for better visibility on modern displays
- Range: 1x (176px wide) to 8x (1408px wide)
- Uses CSS `image-rendering: pixelated` for crisp NES graphics
- **No size constraints**: Image is always rendered at exact scaled size
- **Scrolling at high zoom**: When image is larger than viewport, scrollbars appear
- Coordinate conversion automatically compensates for zoom level

**How Scrolling Preserves Accuracy:**
```
Image size set by JavaScript: width = 176 × 4 = 704px
CSS has no max-width/max-height constraints
→ Image actually rendered at 704px (not shrunk to fit!)
→ Viewer div scrolls when image is too large
→ Click coordinates are relative to full image size
→ Math is perfect: displayWidth always equals imageWidth × zoom
```

**Mathematical Proof:**
```
displayWidth = imageWidth × zoomLevel (enforced by JS, not CSS)
gamePixelX = (clickX / displayWidth) × imageWidth
          = (clickX / (imageWidth × zoom)) × imageWidth
          = clickX / zoom

The zoom factor cancels out, preserving accurate measurements!
```

### Distance Accuracy

The tool uses the exact same formula as the editor's MeasureTool:
- 1 game pixel = 0.5 yards
- 1 yard = 2 game pixels
- Conversion factor: 2.0
- Accurate at all zoom levels (verified by tests)

### Browser Compatibility

- Modern browsers with ES6 module support
- Chrome, Firefox, Safari, Edge
- Mobile-friendly responsive design

## Development

### Testing

Run the included test suite:
```bash
cd web
python3 -m http.server 8000
# Open http://localhost:8000/test.html
```

### Regenerating Images

If course data changes, regenerate images:
```bash
golf-render-web data/chr-ram.bin courses/ web/
```

## License

Part of the golf-fiddling project for reverse engineering NES Open Tournament Golf.
