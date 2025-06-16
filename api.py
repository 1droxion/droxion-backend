import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import {
  FaTrash,
  FaDownload,
  FaClock,
  FaPlus,
  FaVolumeUp,
  FaVolumeMute,
  FaVideo,
} from "react-icons/fa";

function AIChat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [audioOn, setAudioOn] = useState(false);
  const [videoMode, setVideoMode] = useState(false);
  const chatRef = useRef(null);

  useEffect(() => {
    chatRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;
    const userMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await axios.post("https://droxion-backend.onrender.com/chat", {
        prompt: input,
      });
      const reply = res.data.reply;
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);

      if (audioOn) {
        const audioRes = await axios.post("/speak", { text: reply });
        const audio = new Audio(audioRes.data.url);
        audio.play();
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "❌ Error: Something went wrong." },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleAudio = () => setAudioOn(!audioOn);
  const toggleVideoMode = () => setVideoMode(!videoMode);
  const downloadChat = () => {
    const text = messages
      .map((m) => `${m.role === "user" ? "You" : "AI"}: ${m.content}`)
      .join("\n\n");
    const blob = new Blob([text], { type: "text/plain" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "chat.txt";
    link.click();
  };
  const clearChat = () => setMessages([]);

  return (
    <div className="bg-black text-white min-h-screen flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-gray-700">
        <div className="text-lg font-bold">
          💬 <span className="text-white">AI Chat (Droxion)</span>
        </div>
        <div className="flex items-center gap-4 text-white text-md">
          <FaClock title="History" className="cursor-pointer" />
          <FaPlus title="New Chat" className="cursor-pointer" onClick={clearChat} />
          <FaTrash title="Clear Chat" className="cursor-pointer" onClick={clearChat} />
          <FaDownload title="Download Chat" className="cursor-pointer" onClick={downloadChat} />
          {audioOn ? (
            <FaVolumeUp title="Voice On" className="cursor-pointer" onClick={toggleAudio} />
          ) : (
            <FaVolumeMute title="Voice Off" className="cursor-pointer" onClick={toggleAudio} />
          )}
          <FaVideo
            title="Avatar Mode"
            className={`cursor-pointer ${videoMode ? "text-gray-400" : ""}`}
            onClick={toggleVideoMode}
          />
        </div>
      </div>

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.map((msg, index) => (
          <div
            key={index}
            className={`max-w-[75%] px-4 py-3 rounded-xl shadow 
              ${msg.role === "user"
                ? "bg-white text-black ml-auto"
                : "bg-[#1f1f1f] text-white mr-auto"}`}
          >
            {msg.content}
          </div>
        ))}
        {isLoading && <div className="text-gray-500">Typing...</div>}
        <div ref={chatRef} />
      </div>

      {/* Input area */}
      <div className="p-3 border-t border-gray-700">
        <div className="flex items-center gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Type or say anything..."
            className="flex-1 bg-[#1a1a1a] text-white p-3 rounded-lg border border-gray-600 focus:outline-none resize-none"
            rows={1}
          />
          <button
            onClick={handleSend}
            className="bg-white hover:bg-gray-200 text-black font-bold py-2 px-4 rounded"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
}

export default AIChat;
