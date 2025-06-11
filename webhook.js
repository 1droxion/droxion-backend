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

// Stripe requires raw body for webhooks
app.post(
  "/webhook",
  bodyParser.raw({ type: "application/json" }),
  async (req, res) => {
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
      const plan = session.metadata?.plan || "pro"; // default to pro if missing

      console.log(`✅ Payment complete: ${customerEmail} → ${plan}`);

      // Read users.json
      const users = JSON.parse(fs.readFileSync(USER_DB_PATH, "utf8"));

      if (!users[customerEmail]) {
        users[customerEmail] = { coins: 0, plan: "None" };
      }

      let coinsToAdd = 0;
      if (plan === "starter") coinsToAdd = 50;
      if (plan === "pro") coinsToAdd = 150;
      if (plan === "business") coinsToAdd = 400;

      users[customerEmail].coins = (users[customerEmail].coins || 0) + coinsToAdd;
      users[customerEmail].plan = plan;

      // Save users.json
      fs.writeFileSync(USER_DB_PATH, JSON.stringify(users, null, 2));

      console.log(`🪙 ${coinsToAdd} coins added to ${customerEmail}`);
    }

    res.json({ received: true });
  }
);

// Test
app.get("/", (req, res) => {
  res.send("🔁 Stripe webhook is running.");
});

const PORT = process.env.PORT || 4242;
app.listen(PORT, () => console.log(`🚀 Webhook server listening on port ${PORT}`));
