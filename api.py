@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        # Handle CORS preflight request
        return '', 200

    data = request.json
    prompt = data.get("prompt", "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required."}), 400

    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
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

        result = response.json()
        reply = result["choices"][0]["message"]["content"]
        return jsonify({"reply": reply})

    except Exception as e:
        print("❌ Chat Error:", e)
        return jsonify({"error": "Chat generation failed."}), 500
