// FULL WORKING CODE
import express from "express";
import Stripe from "stripe";
import dotenv from "dotenv";
import cors from "cors";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);

// Plan to price & coin map
const PLAN_MAP = {
  pro: {
    priceId: "price_1RXu8bFFxVsSG3xLh3vcO1j0",
    coins: 100,
  },
  business: {
    priceId: "price_1RXu8bFFxVsSG3xLl0Nsd9hp",
    coins: 250,
  },
};

app.post("/create-checkout-session", async (req, res) => {
  try {
    const { email, plan } = req.body;
    const selectedPlan = PLAN_MAP[plan];

    if (!selectedPlan) {
      return res.status(400).json({ error: "Invalid plan selected" });
    }

    const session = await stripe.checkout.sessions.create({
      payment_method_types: ["card"],
      mode: "subscription",
      customer_email: email,
      line_items: [
        {
          price: selectedPlan.priceId,
          quantity: 1,
        },
      ],
      success_url: "http://localhost:5173/success?session_id={CHECKOUT_SESSION_ID}",
      cancel_url: "http://localhost:5173/plans",
      metadata: {
        email,
        plan,
        coins: selectedPlan.coins.toString(),
      },
    });

    res.json({ url: session.url });
  } catch (err) {
    console.error("❌ Stripe session error:", err);
    res.status(500).json({ error: "Could not create Stripe session" });
  }
});

app.get("/", (req, res) => {
  res.send("✅ Stripe checkout session running.");
});

const PORT = process.env.PORT || 4243;
app.listen(PORT, () => {
  console.log(`🚀 Stripe session server running at http://localhost:${PORT}`);
});
