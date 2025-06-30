// ✅ Droxion Stripe Webhook Server – by Dhruv Patel

import express from "express";
import Stripe from "stripe";
import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import bodyParser from "body-parser";

dotenv.config();

const app = express();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
const USER_DB_PATH = path.join(process.cwd(), "users.json");

// ✅ Stripe requires raw body for webhooks
app.post(
  "/stripe-webhook",
  bodyParser.raw({ type: "application/json" }),
  async (req, res) => {
    const sig = req.headers["stripe-signature"];
    const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET;

    let event;
    try {
      event = stripe.webhooks.constructEvent(req.body, sig, endpointSecret);
    } catch (err) {
      console.error("❌ Stripe Webhook Error:", err.message);
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    if (event.type === "checkout.session.completed") {
      const session = event.data.object;
      const customerEmail = session.customer_email;
      const plan = session.metadata?.plan || "pro";

      console.log(`✅ Payment Success: ${customerEmail} → ${plan}`);

      // Load or initialize user DB
      let users = {};
      if (fs.existsSync(USER_DB_PATH)) {
        users = JSON.parse(fs.readFileSync(USER_DB_PATH, "utf8"));
      }

      if (!users[customerEmail]) {
        users[customerEmail] = { coins: 0, plan: "None" };
      }

      let coinsToAdd = 0;
      if (plan === "starter") coinsToAdd = 50;
      else if (plan === "pro") coinsToAdd = 150;
      else if (plan === "business") coinsToAdd = 400;

      users[customerEmail].coins += coinsToAdd;
      users[customerEmail].plan = plan;

      fs.writeFileSync(USER_DB_PATH, JSON.stringify(users, null, 2));
      console.log(`🪙 Added ${coinsToAdd} coins to ${customerEmail}`);
    }

    res.json({ received: true });
  }
);

// ✅ Simple Test Route
app.get("/", (req, res) => {
  res.send("🟢 Droxion Stripe Webhook is running.");
});

const PORT = process.env.PORT || 4242;
app.listen(PORT, () => console.log(`🚀 Webhook server listening on port ${PORT}`));
