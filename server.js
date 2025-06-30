import express from "express";
import Stripe from "stripe";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import bodyParser from "body-parser";

dotenv.config();

const app = express();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
const PAID_USERS_PATH = path.join(process.cwd(), "paid_users.json");

// Enable raw for webhook, and json for other routes
app.use("/webhook", bodyParser.raw({ type: "application/json" }));
app.use(bodyParser.json());

/**
 * ✅ Stripe Webhook → mark user_id as paid
 */
app.post("/webhook", async (req, res) => {
  const sig = req.headers["stripe-signature"];
  const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET;

  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, sig, endpointSecret);
  } catch (err) {
    console.error("❌ Webhook error:", err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  if (event.type === "checkout.session.completed") {
    const session = event.data.object;

    // Get user_id from session metadata
    const user_id = session.metadata?.user_id;
    if (!user_id) {
      console.warn("❌ No user_id in metadata");
      return res.status(400).send("Missing user_id");
    }

    // Mark user_id as paid
    let paidUsers = {};
    if (fs.existsSync(PAID_USERS_PATH)) {
      paidUsers = JSON.parse(fs.readFileSync(PAID_USERS_PATH, "utf8"));
    }

    paidUsers[user_id] = { paid: true, date: new Date().toISOString() };
    fs.writeFileSync(PAID_USERS_PATH, JSON.stringify(paidUsers, null, 2));

    console.log(`✅ User ${user_id} marked as paid`);
  }

  res.json({ received: true });
});

/**
 * ✅ Frontend check: is user paid?
 */
app.post("/check-paid", (req, res) => {
  const { user_id } = req.body;

  if (!user_id) {
    return res.status(400).json({ error: "Missing user_id" });
  }

  let paidUsers = {};
  if (fs.existsSync(PAID_USERS_PATH)) {
    paidUsers = JSON.parse(fs.readFileSync(PAID_USERS_PATH, "utf8"));
  }

  const isPaid = paidUsers[user_id]?.paid === true;
  return res.json({ paid: isPaid });
});

/**
 * 🧪 Simple test
 */
app.get("/", (req, res) => {
  res.send("✅ Droxion Stripe backend running.");
});

const PORT = process.env.PORT || 4242;
app.listen(PORT, () => console.log(`🚀 Droxion backend listening on ${PORT}`));
