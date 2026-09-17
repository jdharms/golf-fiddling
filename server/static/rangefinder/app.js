import { GreenModal } from "./green-modal.js";
import { MeasurementState } from "./measure.js";
import { OverlayRenderer } from "./renderer.js";
import { makeT } from "./strings.js";
import { UIController } from "./ui.js";

const root = document.getElementById("rangefinder");
const t = makeT("rangefinder-strings");
const text = {
  holeOption: (number) => t("rangefinder.script.hole_option", { number }),
  holeInfo: (par, distance) => t("rangefinder.script.hole_info", { par, distance }),
  distanceEmpty: () => t("rangefinder.script.distance_empty"),
  distance: (distance) => t("rangefinder.script.distance", { distance: distance.toFixed(1) }),
  zoom: (level) => t("rangefinder.script.zoom", { level }),
  segment: (distance) => t("rangefinder.script.segment", { distance: distance.toFixed(1) }),
  flag: (current, total) => t("rangefinder.script.flag", { current, total }),
  permalinkCopied: () => t("rangefinder.script.permalink_copied"),
  permalinkFailed: () => t("rangefinder.script.permalink_failed"),
};

function resolveAssetPaths(metadata, metadataUrl) {
  for (const course of Object.values(metadata.courses)) {
    for (const hole of course.holes) {
      hole.image = new URL(hole.image, metadataUrl).href;
      hole.green_image = new URL(hole.green_image, metadataUrl).href;
      hole.flag_images = hole.flag_images.map((path) => new URL(path, metadataUrl).href);
    }
  }
  return metadata;
}

function pointOnImage(event, ui) {
  const rect = ui.holeImage.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * ui.currentHole.width,
    y: ((event.clientY - rect.top) / rect.height) * ui.currentHole.height,
  };
}

function locationFromUrl(metadata) {
  const params = new URLSearchParams(window.location.search);
  const requestedCourse = params.get("course");
  const courseId = Object.hasOwn(metadata.courses, requestedCourse)
    ? requestedCourse
    : Object.keys(metadata.courses)[0];
  const course = metadata.courses[courseId];
  const requestedHole = Number(params.get("hole"));
  const holeNumber = course.holes.some((hole) => hole.number === requestedHole)
    ? requestedHole
    : course.holes[0].number;
  return { courseId, holeNumber };
}

function updatePermalink(courseId, holeNumber) {
  const url = new URL(window.location.href);
  url.searchParams.set("course", courseId);
  url.searchParams.set("hole", String(holeNumber));
  window.history.replaceState(window.history.state, "", url);
  document.getElementById("permalink-status").textContent = "";
}

async function initialize() {
  try {
    const metadataUrl = new URL(root.dataset.metadataUrl, document.baseURI);
    const response = await fetch(metadataUrl);
    if (!response.ok) throw new Error(`metadata request returned ${response.status}`);
    const metadata = resolveAssetPaths(await response.json(), metadataUrl);
    const initialLocation = locationFromUrl(metadata);
    const state = new MeasurementState();
    const renderer = new OverlayRenderer(document.getElementById("overlay-canvas"), text.segment);
    const ui = new UIController(metadata, state, renderer, text, updatePermalink);
    const greenModal = new GreenModal(text.flag);
    const container = document.querySelector(".rangefinder-image-container");

    container.addEventListener("click", (event) => {
      if (event.target !== ui.holeImage) return;
      const point = pointOnImage(event, ui);
      state.addPoint(point.x, point.y);
      ui.updateDisplay();
    });
    container.addEventListener("contextmenu", (event) => {
      if (event.target !== ui.holeImage) return;
      event.preventDefault();
      state.clearPoints();
      ui.updateDisplay();
    });
    container.addEventListener("mousemove", (event) => {
      if (event.target !== ui.holeImage) return;
      const point = pointOnImage(event, ui);
      ui.updatePreview(point.x, point.y);
    });
    container.addEventListener("mouseleave", () => ui.clearPreview());
    document.getElementById("green-view").addEventListener("click", () => {
      if (ui.currentHole) greenModal.open(ui.currentHole, ui.zoomLevel);
    });
    document.getElementById("copy-permalink").addEventListener("click", async () => {
      const status = document.getElementById("permalink-status");
      try {
        await navigator.clipboard.writeText(window.location.href);
        status.textContent = text.permalinkCopied();
      } catch (error) {
        console.warn("Could not copy rangefinder permalink", error);
        status.textContent = text.permalinkFailed();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (greenModal.isOpen) {
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") event.preventDefault();
        if (event.key === "ArrowLeft") greenModal.previousFlag();
        if (event.key === "ArrowRight") greenModal.nextFlag();
        return;
      }
      if (event.target.closest("input, select, textarea, button") || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === "ArrowLeft") ui.previousHole();
      if (event.key === "ArrowRight") ui.nextHole();
      if (event.key.toLowerCase() === "g" && ui.currentHole) greenModal.open(ui.currentHole, ui.zoomLevel);
    });

    ui.loadHole(initialLocation.courseId, initialLocation.holeNumber);
    root.dataset.state = "ready";
  } catch (error) {
    console.error("Failed to initialize rangefinder", error);
    root.dataset.state = "error";
  }
}

initialize();
