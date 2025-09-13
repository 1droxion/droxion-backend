// server/realtime_images_patch.js
// Works with Express. Attach as the FIRST handler for POST /realtime.

import { imageFreeSearch } from "./imageSearch_free.js";

/**
 * Middleware: handles images intent. If not images, falls through to next().
 * Usage in your server:
 *   app.post("/realtime", imagesIntent, yourExistingRealtimeHandler);
 */
export async function imagesIntent(req, res, next) {
  try {
    const { query = "", intent = "" } = req.body || {};
    if (intent !== "images") return next();

    const q = (query || "").replace(/^images?:\s*/i, "").trim() || "nature landscape";
    const { images, sources } = await imageFreeSearch(q);

    return res.json({
      markdown: `### Image results for **${q}**`,
      cards: [
        { type: "images-grid", images },           // grid tiles
        { type: "sources", links: sources }        // source pills
      ],
      steps: [
        "Searched Wikipedia thumbnails",
        "Added Unsplash Source fallback",
        "Merged, deduped, and returned 24 tiles"
      ]
    });
  } catch (err) {
    console.error("imagesIntent error:", err);
    return res.status(500).json({ error: "images intent failed" });
  }
}

/* ---------- CommonJS version (if your server uses require) ----------
const { imageFreeSearch } = require("./imageSearch_free.js");
exports.imagesIntent = async function (req, res, next) { ...same body... };
--------------------------------------------------------------------- */