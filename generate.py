import React, { useState, useEffect } from "react";
import axios from "axios";

function Generator() {
  const [formData, setFormData] = useState({
    mode: "Auto",
    topic: "",
    language: "English",
    userScript: "",
    voice: "onyx",
    style: "Cinematic",
    length: "Medium",
    captions: "Word-by-Word",
    subtitlePosition: "Bottom",
    branding: "Yes",
    musicVolume: "Medium Volume",
    clipCount: 10,
    voiceSpeed: 1.0,
  });

  const [isLoading, setIsLoading] = useState(false);
  const [videoUrl, setVideoUrl] = useState("");
  const [credits, setCredits] = useState(0);
  const [videoLimitReached, setVideoLimitReached] = useState(false);

  useEffect(() => {
    axios
      .get(`${import.meta.env.VITE_BACKEND_URL || "https://droxion-backend.onrender.com"}/user-stats`)
      .then((res) => {
        const stats = res.data;
        setCredits(stats.credits);
        if (stats.videosThisMonth >= stats.plan.videoLimit) {
          setVideoLimitReached(true);
        }
      })
      .catch((err) => {
        console.warn("⚠️ Could not fetch usage stats.", err);
      });
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleGenerate = async () => {
    if (videoLimitReached) {
      alert("🚫 You've reached your video generation limit. Please upgrade your plan.");
      return;
    }

    if (!formData.topic.trim()) {
      alert("❗ Please enter a topic or prompt.");
      return;
    }

    setIsLoading(true);
    setVideoUrl("");

    try {
      const res = await axios.post(
        `${import.meta.env.VITE_BACKEND_URL || "https://droxion-backend.onrender.com"}/generate-veo`,
        formData
      );
      if (res.data.videoUrl) {
        setVideoUrl(`${import.meta.env.VITE_BACKEND_URL || "https://droxion-backend.onrender.com"}${res.data.videoUrl}`);
      } else {
        alert("⚠️ No video returned.");
      }
    } catch (err) {
      console.error("❌ Generate Error:", err);
      alert("❌ Something went wrong.");
    }

    setIsLoading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0f0c29] via-[#302b63] to-[#24243e] text-white p-6">
      <div className="max-w-7xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-green-400 via-purple-400 to-pink-500 bg-clip-text text-transparent">
            ✨ Create Magical AI Reels
          </h1>
          <div className="bg-black px-3 py-1 rounded text-green-400 font-semibold text-sm border border-green-600">
            💰 {credits}
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-10">
          {/* Form Panel */}
          <div className="space-y-4 backdrop-blur-md bg-white/5 p-6 rounded-xl shadow-lg border border-purple-600/30">
            <input
              name="topic"
              value={formData.topic}
              onChange={handleChange}
              placeholder="💡 Enter prompt like 'A futuristic AI rising from digital particles'"
              className="input"
            />

            <div className="grid grid-cols-2 gap-4">
              <select name="language" value={formData.language} onChange={handleChange} className="input">
                <option>English</option>
                <option>Hindi</option>
                <option>Gujarati</option>
              </select>

              <select name="voice" value={formData.voice} onChange={handleChange} className="input">
                <option value="onyx">Onyx</option>
                <option value="nova">Nova</option>
                <option value="echo">Echo</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <select name="style" value={formData.style} onChange={handleChange} className="input">
                <option>Cinematic</option>
                <option>Emotional</option>
                <option>Fast-Paced</option>
              </select>

              <select name="length" value={formData.length} onChange={handleChange} className="input">
                <option>Short</option>
                <option>Medium</option>
                <option>Long</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <select name="captions" value={formData.captions} onChange={handleChange} className="input">
                <option>Word-by-Word</option>
                <option>Sentence</option>
                <option>None</option>
              </select>

              <select name="subtitlePosition" value={formData.subtitlePosition} onChange={handleChange} className="input">
                <option>Bottom</option>
                <option>Center</option>
                <option>Top</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <select name="branding" value={formData.branding} onChange={handleChange} className="input">
                <option>Yes</option>
                <option>No</option>
              </select>

              <select name="musicVolume" value={formData.musicVolume} onChange={handleChange} className="input">
                <option>Low Volume</option>
                <option>Medium Volume</option>
                <option>High Volume</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <input
                type="number"
                name="clipCount"
                value={formData.clipCount}
                onChange={handleChange}
                className="input"
              />
              <input
                type="number"
                name="voiceSpeed"
                step="0.1"
                value={formData.voiceSpeed}
                onChange={handleChange}
                className="input"
              />
            </div>
          </div>

          {/* Preview Panel */}
          <div className="flex flex-col items-center justify-center space-y-6 text-center">
            {videoUrl ? (
              <video src={videoUrl} controls className="w-full rounded-2xl shadow-2xl border border-purple-500/30" />
            ) : (
              <div className="text-gray-400 italic animate-pulse">
                🎞️ Your magical reel will appear here after generation.
              </div>
            )}

            <button
              onClick={handleGenerate}
              disabled={isLoading || videoLimitReached}
              className={`w-full py-4 px-8 text-xl font-bold rounded-full transition-all shadow-lg ${
                isLoading || videoLimitReached
                  ? "bg-gray-500 cursor-not-allowed"
                  : "bg-gradient-to-r from-purple-500 to-pink-500 hover:from-pink-600 hover:to-purple-600"
              }`}
            >
              {videoLimitReached
                ? "🚫 Limit Reached"
                : isLoading
                ? "Creating Magic..."
                : "✨ Generate Magical Reel"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Generator;
