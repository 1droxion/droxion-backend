@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return '', 200

    try:
        data = request.json
        print("📩 Incoming data:", data)

        prompt = data.get("prompt", "").strip()
        if not prompt:
            print("❌ Prompt missing")
            return jsonify({"error": "Prompt is required."}), 400

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("❌ Missing OPENROUTER_API_KEY in env")
            return jsonify({"error": "OpenRouter API key is missing."}), 500

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "openrouter/openchat",
            "messages": [
                {"role": "system", "content": "You are an assistant powered by Droxion."},
                {"role": "user", "content": prompt}
            ]
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        )

        print("📦 OpenRouter response status:", response.status_code)
        result = response.json()
        print("✅ OpenRouter result:", result)

        # Handle OpenRouter errors safely
        if "choices" not in result or not result["choices"]:
            return jsonify({"reply": "Sorry, something went wrong with the AI response."})

        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})

    except Exception as e:
        print("❌ Chat Exception:", e)
        return jsonify({"error": "Internal Server Error"}), 500
