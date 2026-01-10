# Zoom Coordinate System Fix

## The Problem

When the image was zoomed to 4x or higher, CSS `max-width` and `max-height` constraints were shrinking the image to fit the viewport. This broke the coordinate conversion math.

### What Was Happening

1. UI sets image size: `width = 176 × 4 = 704px`
2. CSS shrinks it: `max-height: calc(100vh - 200px)` → displayed at 500px (example)
3. Coordinate conversion assumes 704px: `gameX = (clickX / 704) × 176`
4. But actual displayed size is 500px, so clicks are misaligned! ❌

### The Math Breakdown

**Expected (what ui.js calculated):**
```
scaledWidth = 176 × 4 = 704px
scaledHeight = 304 × 4 = 1216px
```

**Actual (after CSS shrinking):**
```
displayedWidth = 704px (if fits horizontally)
displayedHeight = 500px (shrunk by CSS max-height)
```

**Click at bottom of screen:**
```
clickY = 500 (bottom of displayed image)
gameY = (500 / 1216) × 304 = 124.7 ← WRONG!
Should be: (500 / 500) × (500/4) = 125 pixels down at current zoom
```

The conversion formula expected the image to be 1216px tall, but it was actually only 500px tall.

## The Solution

**Remove all size constraints from the image!**

### Before (Broken):
```css
#hole-image {
  display: block;
  max-width: 100%;
  max-height: calc(100vh - 200px);
  height: auto;
}
```

### After (Fixed):
```css
#hole-image {
  display: block;
  /* No max-width or max-height */
  /* Size controlled by ui.js: width/height = imageWidth/Height × zoomLevel */
  image-rendering: pixelated;
}
```

### How It Works Now

1. `ui.js` sets **explicit** width/height: `image.style.width = '704px'`
2. CSS has **no constraints** → image is exactly 704px
3. If too big for viewport → `.viewer { overflow: auto }` adds scrollbars
4. Coordinate math is **perfect**: displayed size always equals expected size ✓

## Testing

To verify the fix works:

1. Open the web app
2. Zoom to 4x or higher
3. Click at the top of the course → waypoint appears at click position ✓
4. Click at the bottom → waypoint appears at click position ✓
5. Measure tee to green → distance matches editor ✓

### Key Verification Points

- Image is never shrunk by CSS (check DevTools: computed size = style.width)
- Scrollbars appear when image is too large for viewport
- Clicking anywhere on the visible image places waypoints accurately
- Distance calculations match at all zoom levels (1x through 8x)

## Why This Approach Is Best

### ✓ Simple and Robust
- Image size = `imageWidth × zoom` (no exceptions)
- No "detect and reduce zoom" complexity
- No special cases or browser-specific hacks

### ✓ Predictable Behavior
- Users expect high zoom → big image → scrolling
- Familiar interaction pattern (like zooming images in photo viewers)
- No surprising "can't zoom more" limits based on screen size

### ✓ Math Stays Clean
- `gamePixelX = (clickX / displayWidth) × imageWidth`
- Always true because `displayWidth` always equals `imageWidth × zoom`
- No need to check if CSS modified the size

### ✓ Works on All Screens
- Small screens: scroll at high zoom (expected)
- Large screens: no scrolling until very high zoom
- No screen-size-specific logic needed

## Alternative Approaches (Rejected)

### ❌ Auto-Reduce Zoom
Detect when image won't fit and reduce zoom automatically.

**Problems:**
- Complex: need to measure viewport, compare to scaled size
- Unpredictable: zoom level changes based on window size
- Confusing: user clicks "4x" but gets "3x"
- Still needs max-constraints for "just barely fits" case

### ❌ Disable Zoom-In When Won't Fit
Prevent zooming beyond what fits on screen.

**Problems:**
- Limiting: can't zoom to examine details on small screens
- Inconsistent: max zoom depends on screen size, hole height
- Still doesn't solve "resize window" case

### ❌ Scale Canvas Separately
Keep CSS constraints, adjust coordinate conversion math.

**Problems:**
- Complex: need to read actual displayed size, compare to expected
- Brittle: breaks if CSS changes or browser renders differently
- More moving parts = more bugs

## Conclusion

**The fix is simple: remove CSS size constraints, let the image scroll.**

This is the standard approach for zoomable images and works perfectly for our use case.
