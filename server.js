import express from "express";
import Stripe from "stripe";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import cors from "cors";
import bodyParser from "body-parser";

dotenv.config();

const app = express();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
const USER_DB_PATH = path.join(process.cwd(), "users.json");

// ✅ Allow frontend CORS
app.use(cors({
  origin: "https://www.droxion.com",
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type"]
}));

// ✅ Stripe Webhook (must come BEFORE express.json)
app.post("/stripe-webhook", bodyParser.raw({ type: "application/json" }), (req, res) => {
  const sig = req.headers["stripe-signature"];
  const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET;

  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, sig, endpointSecret);
  } catch (err) {
    console.error("❌ Webhook Error:", err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  if (event.type === "checkout.session.completed") {
    const session = event.data.object;
    const userId = session.metadata?.user_id || "";
    const plan = session.metadata?.plan || "pro";

    console.log(`✅ Payment complete for user_id: ${userId} → plan: ${plan}`);

    let users = {};
    if (fs.existsSync(USER_DB_PATH)) {
      users = JSON.parse(fs.readFileSync(USER_DB_PATH, "utf8"));
    }

    if (!users[userId]) {
      users[userId] = { coins: 0, plan: "none" };
    }

    // 🪙 Add coins based on plan
    let coins = 0;
    if (plan === "starter") coins = 50;
    else if (plan === "pro") coins = 150;
    else if (plan === "business") coins = 400;

    users[userId].paid = true;
    users[userId].plan = plan;
    users[userId].coins = (users[userId].coins || 0) + coins;

    fs.writeFileSync(USER_DB_PATH, JSON.stringify(users, null, 2));
    console.log(`🪙 ${coins} coins added to ${userId}`);
  }

  res.json({ received: true });
});

// ✅ Normal body parser after webhook
app.use(express.json());

// ✅ Check if user has paid
app.post("/check-paid", (req, res) => {
  const { user_id } = req.body;
  if (!user_id) return res.status(400).json({ paid: false });

  let users = {};
  if (fs.existsSync(USER_DB_PATH)) {
    users = JSON.parse(fs.readFileSync(USER_DB_PATH, "utf8"));
  }

  const paid = users[user_id]?.paid === true;
  res.json({ paid });
});

// ✅ Track usage
app.post("/track", (req, res) => {
  const log = {
    user_id: req.body.user_id,
    action: req.body.action,
    input: req.body.input,
    timestamp: req.body.timestamp
  };

  console.log("📩 TRACK:", log);
  res.json({ ok: true });
});

// ✅ Health check
app.get("/", (req, res) => {
  res.send("🚀 Droxion backend is running.");
});

const PORT = process.env.PORT || 4242;
app.listen(PORT, () => {
  console.log(`✅ Server running on http://localhost:${PORT}`);
});
