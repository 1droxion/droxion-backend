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

// ✅ CORS setup to allow frontend
app.use(cors({
  origin: "https://www.droxion.com",
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type"]
}));

app.use(express.json());

// ✅ Allow Stripe raw body for webhook only
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
    const customerEmail = session.customer_email;
    const userId = session.metadata?.user_id || "";

    console.log(`✅ Payment from ${customerEmail} (ID: ${userId})`);

    const users = JSON.parse(fs.readFileSync(USER_DB_PATH, "utf8"));
    users[userId] = { paid: true };
    fs.writeFileSync(USER_DB_PATH, JSON.stringify(users, null, 2));

    console.log("🪙 User marked as paid.");
  }

  res.json({ received: true });
});

// ✅ /check-paid route
app.post("/check-paid", (req, res) => {
  const { user_id } = req.body;
  if (!user_id) return res.status(400).json({ paid: false });

  let users = {};
  if (fs.existsSync(USER_DB_PATH)) {
    users = JSON.parse(fs.readFileSync(USER_DB_PATH, "utf8"));
  }

  const isPaid = users[user_id]?.paid === true;
  res.json({ paid: isPaid });
});

// ✅ Test route
app.get("/", (req, res) => {
  res.send("🚀 Droxion backend is live.");
});

const PORT = process.env.PORT || 4242;
app.listen(PORT, () => console.log(`✅ Server running on http://localhost:${PORT}`));
