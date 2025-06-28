from flask import Flask, request
from flask_cors import CORS
import os, json
import stripe

# === Configure Flask ===
app = Flask(__name__)
CORS(app)

# === Stripe Setup ===
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

# === Webhook Route ===
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception as e:
        print("❌ Stripe Webhook Error:", e)
        return "", 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        customer_email = session.get("customer_email")
        ip = request.remote_addr

        # === Save VIP IP ===
        with open("vip_users.json", "r+") as f:
            try:
                data = json.load(f)
            except:
                data = []

            if ip not in data:
                data.append(ip)
                f.seek(0)
                json.dump(data, f)
                f.truncate()

        print("✅ VIP Unlocked for IP:", ip)

    return "", 200

# === Root Test Route (optional) ===
@app.route("/")
def index():
    return "Winkly Backend is Running ✅"

# === Start Server ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
