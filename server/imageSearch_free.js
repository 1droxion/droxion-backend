// server/realtime.js
import express from "express";
import { imagesIntent } from "./realtime_images_patch.js";

const router = express.Router();

// Ensure body parsing happens in your app.js/server.js (app.use(express.json()))
// If not, uncomment the next line for this router:
// router.use(express.json());

// Attach the images middleware BEFORE the handler
router.post("/", imagesIntent, async (req, res) => {
  try {
    // If imagesIntent handled it, return immediately
    if (res.locals.imagesPayload) {
      return res.json(res.locals.imagesPayload);
    }

    const { intent = "", query = "" } = req.body || {};
    const i = (intent || "").toLowerCase();

    if (i === "news") {
      // TODO: your real news code here
      return res.json({
        markdown: `Top news for **${query}**`,
        cards: []
      });
    }

    if (i === "weather") {
      // TODO: your real weather code here
      // Example minimal weather card (UI normalizes this)
      return res.json({
        markdown: `Weather`,
        cards: [{
          type: "weather",
          title: "Weather",
          subtitle: "Now",
          temp_c: 28, temp_f: 82,
          feels_c: 30, feels_f: 86,
          humidity: 65,
          wind_kph: 12,
          hourly: [],
          daily: []
        }]
      });
    }

    if (i === "crypto") {
      // TODO: your real crypto code
      return res.json({
        markdown: `Crypto prices`,
        cards: []
      });
    }

    // default / fallback to chat-style
    return res.json({
      markdown: "Default chat response",
      cards: []
    });
  } catch (err) {
    console.error("Realtime error:", err);
    res.status(500).json({ error: "Realtime failed" });
  }
});

export default router;