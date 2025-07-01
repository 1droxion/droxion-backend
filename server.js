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

// ✅ CORS for Droxion frontend
app.use(cors({
  origin: "https://www.droxion.com",
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type"]
}));

// ✅ JSON parser (after webhook)
app.use(express.json());

// ✅ Stripe Checkout Session creation
app.post("/create-checkout-session", async (req, res) => {
  const { user_id } = req.body;
  if (!user_id) return res.status(400).json({ error: "Missing user_id" });

  try {
    const session = await stripe.checkout.sessions.create({
      payment_method_types: ["card"],
      line_items: [{
        price_data: {
          currency: "usd",
          product_data: { name: "Droxion Access – 1-Time Unlock" },
          unit_amount: 199
        },
        quantity: 1
      }],
      mode: "payment",
      success_url: "https://www.droxion.com/chatboard",
      cancel_url: "https://www.droxion.com",
      metadata: { user_id }
    });

    res.json({ url: session.url });
  } catch (err) {
    console.error("❌ Checkout error:", err.message);
    res.status(500).json({ error: "Checkout session failed" });
  }
});

// ✅ Stripe Webhook (must come BEFORE express.json)
app.post("/stripe-webhook", bodyParser.raw({ type: "application/json" }), (req, res) => {
  const sig = req.headers["stripe-signature"];
  const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET;

  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, sig, endpointSecret);
  } catch (err) {
    console.error("❌ Webhook signature error:", err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  if (event.type === "checkout.session.completed") {
    const session = event.data.object;
    const userId = session.metadata?.user_id || "";

    console.log(`✅ Payment complete for user_id: ${userId}`);

    let users = {};
    if (fs.existsSync(USER_DB_PATH)) {
      users = JSON.parse(fs.readFileSync(USER_DB_PATH, "utf8"));
    }

    users[userId] = { paid: true };
    fs.writeFileSync(USER_DB_PATH, JSON.stringify(users, null, 2));

    console.log("🪙 User marked as paid.");
  }

  res.json({ received: true });
});

// ✅ Verify if user is paid
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

// ✅ Health check
app.get("/", (req, res) => {
  res.send("🚀 Droxion backend is live.");
});

const PORT = process.env.PORT || 4242;
app.listen(PORT, () => console.log(`✅ Server running at http://localhost:${PORT}`));
