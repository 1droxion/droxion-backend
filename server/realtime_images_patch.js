import express from "express";
import { imagesIntent } from "./server/realtime_images_patch.js";  // <== NEW

const router = express.Router();

// Attach middleware first
router.post("/", imagesIntent, async (req, res) => {
  try {
    const { query = "", intent = "" } = req.body || {};

    // ======= Your existing realtime code =======
    // Example:
    if (intent === "news") {
      // your news logic here...
      return res.json({ markdown: "Top news…", cards: [] });
    }

    if (intent === "weather") {
      // your weather logic here...
      return res.json({ markdown: "Weather details…", cards: [] });
    }

    if (intent === "crypto") {
      // crypto logic
      return res.json({ markdown: "Crypto prices…", cards: [] });
    }

    // fallback to chat
    return res.json({ markdown: "Default chat response", cards: [] });

  } catch (err) {
    console.error("Realtime error:", err);
    res.status(500).json({ error: "Realtime failed" });
  }
});

export default router;