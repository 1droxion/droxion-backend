import React, { useState, useEffect } from "react";
import axios from "axios";

function AIImage() {
  const [prompt, setPrompt] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [credits, setCredits] = useState(0);
  const [imageLimitReached, setImageLimitReached] = useState(false);

  useEffect(() => {
    axios
      .get(`${import.meta.env.VITE_BACKEND_URL || "https://droxion-backend.onrender.com"}/user-stats`)
      .then((res) => {
        const stats = res.data;
        setCredits(stats.credits);
        if (stats.imagesThisMonth >= stats.plan.imageLimit) {
          setImageLimitReached(true);
        }
      })
      .catch((err) => {
        console.warn("⚠️ Could not fetch image stats.", err);
      });
  }, []);

  const generateImage = async () => {
    if (imageLimitReached) {
      alert("🚫 You've reached your image generation limit. Please upgrade your plan.");
      return;
    }

    if (!prompt.trim()) {
      alert("⚠️ Please enter a prompt.");
      return;
    }

    setLoading(true);
    setImageUrl("");

    try {
      const response = await axios.post(
        `${import.meta.env.VITE_BACKEND_URL || "https://droxion-backend.onrender.com"}/generate-image`,
        { prompt }
      );

      const url = response.data.url;
      if (url) {
        setImageUrl(url);
      } else {
        alert("⚠️ Failed to get image URL.");
      }
    } catch (err) {
      console.error("❌ Error:", err.response?.data || err.message);
      alert("Image generation failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen px-6 py-10 bg-gradient-to-br from-black via-[#0f0f23] to-black text-white flex flex-col items-center justify-center">
      <div className="flex justify-between w-full max-w-5xl mb-6">
        <h1 className="text-4xl md:text-6xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-500 animate-pulse">
          🪄 Create Stunning AI Images
        </h1>
        <div className="bg-black px-3 py-1 rounded text-green-400 font-semibold text-sm border border-green-600 self-start">
          💰 {credits}
        </div>
      </div>

      <input
        type="text"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="✨ Describe your dream scene..."
        className="w-full max-w-xl p-4 mb-6 rounded-lg text-black shadow-inner border-2 border-blue-500 focus:outline-none focus:ring-4 focus:ring-purple-600 transition-all"
      />

      <button
        onClick={generateImage}
        disabled={loading || imageLimitReached}
        className={`px-8 py-3 font-bold text-lg rounded-xl transition-all bg-gradient-to-r from-green-400 via-cyan-400 to-blue-500 hover:from-pink-500 hover:to-yellow-500 ${
          loading || imageLimitReached ? "opacity-50 cursor-not-allowed" : ""
        }`}
      >
        {imageLimitReached ? "🚫 Limit Reached" : loading ? "🌌 Generating..." : "⚡ Generate Image"}
      </button>

      {imageUrl && (
        <div className="mt-10 w-full flex justify-center">
          <iframe
            src={imageUrl}
            title="Generated AI Image"
            className="rounded-xl border-4 border-purple-500 shadow-2xl w-full max-w-3xl h-[600px]"
          />
        </div>
      )}
    </div>
  );
}

export default AIImage;
