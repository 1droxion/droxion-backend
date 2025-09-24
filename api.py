import React, { useState, useEffect, useRef } from "react";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import {
  FaTrash, FaDownload, FaPlus,
  FaVolumeUp, FaVolumeMute, FaMicrophone,
  FaUpload, FaCamera, FaRegCopy
} from "react-icons/fa";

const API_BASE = "https://droxion-backend.onrender.com";

function AIChat() {
  // -------- State --------
  const [messages, setMessages] = useState([]); // [{role, content, cards?}]
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const [voiceMode, setVoiceMode] = useState(false);
  const [topToolsOpen, setTopToolsOpen] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState(null);

  // dynamic, debounced suggestions (replaces static list)
  const [suggestions, setSuggestions] = useState([]);

  // refs
  const chatEndRef = useRef(null);
  const inputRef = useRef(null);
  const synth = typeof window !== "undefined" ? window.speechSynthesis : null;
  const userId = useRef("");
  const suggestTimer = useRef(null);

  // -------- Helpers --------
  const pushAssistant = (content, extra = {}) =>
    setMessages(prev => [...prev, { role: "assistant", content, ...extra }]);
  const pushUser = (content) =>
    setMessages(prev => [...prev, { role: "user", content }]);

  const logAction = async (action, inputText) => {
    try {
      await axios.post(`${API_BASE}/track`, {
        user_id: userId.current,
        action,
        input: inputText,
        timestamp: new Date().toISOString()
      });
    } catch { /* silent */ }
  };

  const speak = (text) => {
    if (!voiceMode || !text || !synth) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-US";
    synth.cancel();
    synth.speak(u);
  };

  // ---------- YouTube helpers ----------
  const getYouTubeId = (raw) => {
    try {
      const txt = raw.trim();
      if (/^[A-Za-z0-9_-]{11}$/.test(txt)) return txt;
      const hasHttp = /^https?:\/\//i.test(txt);
      const u = new URL(hasHttp ? txt : `https://youtube.com/results?search_query=${encodeURIComponent(txt)}`);
      const host = u.hostname.replace("www.", "");
      if (host.includes("youtube.com")) {
        if (u.searchParams.get("v")) return u.searchParams.get("v");
        const p = u.pathname.split("/").filter(Boolean);
        if (p[0] === "shorts" || p[0] === "embed") return p[1];
      }
      if (host.includes("youtu.be")) {
        const p = u.pathname.split("/").filter(Boolean);
        if (p[0]) return p[0];
      }
    } catch {}
    const m = raw.match(/([A-Za-z0-9_-]{11})/);
    return m ? m[1] : null;
  };

  // ---------- Effects ----------
  useEffect(() => {
    let id = localStorage.getItem("droxion_uid");
    if (!id) {
      id = "user-" + Math.random().toString(36).substring(2, 10);
      localStorage.setItem("droxion_uid", id);
    }
    userId.current = id;
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, typing]);

  // Global styles + glass look + mobile viewport
  useEffect(() => {
    const style = document.createElement("style");
    style.innerHTML = `
      :root { --glass: rgba(255,255,255,0.06); --glass-2: rgba(255,255,255,0.10); --border: rgba(255,255,255,0.12); }
      * { -webkit-tap-highlight-color: transparent; }
      textarea, input { font-size: 16px !important; }
      img, iframe, video { max-width: 100% !important; height: auto !important; }
      .embed-responsive { position: relative; width: 100%; }
      .embed-16by9 { padding-top: 56.25%; }
      .embed-responsive iframe { position: absolute; top:0; left:0; width:100%; height:100%; border:0; }
      .shimmer { background: linear-gradient(90deg, rgba(255,255,255,0.06) 25%, rgba(255,255,255,0.12) 37%, rgba(255,255,255,0.06) 63%);
                 background-size:400% 100%; animation: shimmer 1.4s ease infinite; border-radius: 8px; }
      @keyframes shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }
      .glass { background: var(--glass); border: 1px solid var(--border); backdrop-filter: blur(10px); }
      .glass-2 { background: var(--glass-2); border: 1px solid var(--border); backdrop-filter: blur(10px); }
      textarea { min-height: 40px; line-height: 1.6; }
      .suggestion-box { position: fixed; left: 50%; transform: translateX(-50%); bottom: 88px;
        width: min(960px, calc(100vw - 24px)); background: rgba(20,20,20,.95); border: 1px solid #333;
        border-radius: 10px; padding: 8px; display: grid; gap: 6px; z-index: 45; }
      .suggestion { text-align: left; background: transparent; border: 1px solid #444; border-radius: 8px; padding: 8px; }
    `;
    document.head.appendChild(style);

    let meta = document.querySelector('meta[name="viewport"]');
    if (!meta) {
      meta = document.createElement("meta");
      meta.setAttribute("name", "viewport");
      document.head.appendChild(meta);
    }
    meta.setAttribute("content", "width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover");
    return () => { document.head.removeChild(style); };
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "/" && document.activeElement !== inputRef.current) {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setTopToolsOpen(v => !v);
      }
      if (e.key === "Escape") inputRef.current?.blur();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Autoresize textarea
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [input]);

  // -------- Suggestions (debounced) --------
  useEffect(() => {
    const q = (input || "").trim();
    clearTimeout(suggestTimer.current);
    if (!q) { setSuggestions([]); return; }
    suggestTimer.current = setTimeout(async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/suggest`, { params: { q } });
        setSuggestions((data?.suggestions || []).slice(0, 8));
      } catch { /* silent */ }
    }, 250);
    return () => clearTimeout(suggestTimer.current);
  }, [input]);

  // ---------- Card renderer ----------
  const renderCards = (cards) => {
    if (!cards || !cards.length) return null;
    return (
      <div className="grid grid-cols-1 gap-3">
        {cards.map((c, idx) => {
          // generic "link/news/stock/weather/wiki" support
          if (c.type === "web" || c.type === "news" || c.type === "link" || c.type === "stock" || c.type === "weather" || c.type === "wiki") {
            return (
              <a key={idx} href={c.url} target="_blank" rel="noreferrer"
                 className="block glass rounded-lg p-3 hover:bg-white/10 transition">
                {c.image && <img src={c.image} alt="" className="w-full rounded mb-2" loading="lazy" onError={(e)=>e.currentTarget.style.display="none"} />}
                <div className="text-sm font-semibold leading-snug">{c.title}</div>
                <div className="text-xs text-gray-400 mt-1">
                  {c.source || (c.url ? new URL(c.url).hostname.replace('www.','') : "")}{c.time ? ` • ${c.time}` : ""}
                </div>
                {c.snippet && <div className="text-xs text-gray-300 mt-1">{c.snippet}</div>}
                {c.description && <div className="text-xs text-gray-300 mt-1">{c.description}</div>}
                {c.meta && <div className="text-[11px] text-gray-400 mt-1">{c.meta}</div>}
              </a>
            );
          }
          if (c.type === "youtube") {
            const vid = getYouTubeId(c.url || "");
            if (!vid) return null;
            return (
              <div key={idx} className="embed-responsive embed-16by9 rounded overflow-hidden glass">
                <iframe
                  src={`https://www.youtube.com/embed/${vid}`}
                  title={c.title || "YouTube"}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                />
              </div>
            );
          }
          // more robust image card
          const imgUrl = c.image_url || c.url || c.image;
          if (c.type === "image" && imgUrl) {
            return (
              <img
                key={idx}
                src={imgUrl}
                alt=""
                className="w-full rounded glass"
                loading="lazy"
                onError={(e)=>e.currentTarget.style.display="none"}
              />
            );
          }
          if (c.html) return <div key={idx} className="prose prose-invert max-w-none" dangerouslySetInnerHTML={{ __html: c.html }} />;
          if (c.text) return <div key={idx} className="text-sm">{c.text}</div>;
          return null;
        })}
      </div>
    );
  };

  const copyMessage = async (i) => {
    try {
      const msg = messages[i];
      if (!msg) return;
      await navigator.clipboard.writeText(msg.content || "");
      setCopiedIdx(i);
      setTimeout(() => setCopiedIdx(null), 1200);
    } catch {}
  };

  // ---------- Main send ----------
  const handleSend = async (textToSend = input) => {
    const content = textToSend.trim();
    if (!content) return;

    setTyping(true);
    pushUser(content);
    setInput("");
    setSuggestions([]);
    logAction("message", content);
    const lower = content.toLowerCase();

    try {
      // 0) GOOGLE trigger (renders realtime cards on same page)
      if (lower.startsWith("google:")) {
        const q = content.replace(/^google:\s*/i, "");
        try {
          const r = await axios.post(`${API_BASE}/realtime`, { query: q });
          const cards = Array.isArray(r.data?.cards) ? r.data.cards : [];
          const md = r.data?.markdown || r.data?.summary || `Results for **${q}**`;
          pushAssistant(md, { cards });
        } catch {
          pushAssistant("Google preview is unavailable right now.");
        }
        setTyping(false);
        return;
      }

      // 0) SEARCH (explicit trigger "search: ...")
      if (lower.startsWith("search:")) {
        const q = content.replace(/^search:\s*/i, "");
        try {
          const r = await axios.post(`${API_BASE}/search`, { prompt: q });
          const results = (r.data?.results || []).map(it => ({
            type: "web",
            title: it.title,
            url: it.url,
            image: it.image,
            source: it.source,
            snippet: it.snippet
          }));
          if (results.length) {
            pushAssistant(`Here are sources for **${q}**:`, { cards: results });
          } else {
            pushAssistant(`No sources found for **${q}**.`);
          }
        } catch {
          pushAssistant("Search is unavailable right now.");
        }
        setTyping(false);
        return;
      }

      // 0.1) keyword "news" -> backend realtime/news
      if (/\bnews\b/i.test(lower)) {
        try {
          const n = await axios.post(`${API_BASE}/realtime/news`, {});
          const headlines = (n.data?.headlines || []).map(h => ({
            type: "news",
            title: h.title || h,
            url: h.url,
            source: h.source,
            image: h.image,
            time: h.time
          }));
          if (headlines.length) pushAssistant("📰 Top headlines:", { cards: headlines });
          else pushAssistant("Couldn't fetch news right now.");
        } catch {
          pushAssistant("Couldn't fetch news right now.");
        }
        setTyping(false);
        return;
      }

      // 0.2) keyword "link" -> generic search cards
      if (/\blink\b/i.test(lower)) {
        try {
          const r = await axios.post(`${API_BASE}/search`, { prompt: content });
          const results = (r.data?.results || []).map(it => ({
            type: "web",
            title: it.title,
            url: it.url,
            image: it.image,
            source: it.source,
            snippet: it.snippet
          }));
          if (results.length) pushAssistant("🔗 Here are some links:", { cards: results });
          else pushAssistant("No links found.");
        } catch {
          pushAssistant("Couldn't fetch links right now.");
        }
        setTyping(false);
        return;
      }

      // 1) YOUTUBE first (so "YouTube: ..." won't trigger image/chat)
      const ytKW = ["youtube", "yt ", "youtu.be", "youtube.com", "video", "trailer", "shorts", "song", "watch "];
      if (ytKW.some(k => lower.includes(k)) || lower.startsWith("youtube:")) {
        const directId = getYouTubeId(content);
        if (directId) {
          pushAssistant("", { cards: [{ type: "youtube", url: `https://www.youtube.com/watch?v=${directId}` }] });
        } else {
          try {
            const res = await axios.post(`${API_BASE}/search-youtube`, { prompt: content });
            const url = res.data?.url;
            if (url) {
              pushAssistant("", { cards: [{ type: "youtube", url }] });
            } else {
              const r = await axios.post(`${API_BASE}/chat`, { prompt: content });
              const reply = r.data?.reply || "I couldn't find a video for that.";
              pushAssistant(reply);
              speak(reply);
            }
          } catch {
            pushAssistant("YouTube search is unavailable right now.");
          }
        }
        setTyping(false);
        return;
      }

      // 2) IMAGE (robust keys + fallback)
      const imageTrigger = /^(image:|generate( an)? (image|photo|art|picture)|wallpaper|artwork)/i.test(lower)
        || lower.includes(" generate an image");
      if (imageTrigger) {
        try {
          const im = await axios.post(`${API_BASE}/generate-image`, { prompt: content });
          const url =
            im?.data?.image_url ||
            im?.data?.url ||
            im?.data?.image ||
            im?.data?.data?.url ||
            null;
          if (url && typeof url === "string") {
            pushAssistant("", { cards: [{ type: "image", image_url: url }] });
          } else {
            pushAssistant("⚠️ No image returned. Please try again.");
          }
        } catch (err) {
          console.error("Image gen error:", err);
          pushAssistant("⚠️ Image generation failed.");
        }
        setTyping(false);
        return;
      }

      // 3) DEFAULT chat
      const res = await axios.post(`${API_BASE}/chat`, { prompt: content, voiceMode });
      let reply = res.data?.reply || res.data?.text || "";
      if (/who.*(made|created|built)/i.test(content)) {
        reply = "I was created and managed by **Dhruv Patel**, powered by OpenAI.";
      }
      pushAssistant(reply);
      speak(reply);
    } catch (err) {
      console.error(err);
      pushAssistant("⚠️ Error or connection failed.");
    } finally {
      setTyping(false);
    }
  };

  const handlePromptClick = (style) => handleSend(`Generate an image in ${style} style.`);

  const handleMic = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return alert("Mic not supported");
    const recog = new SR();
    recog.lang = "en-US";
    recog.start();
    recog.onresult = e => setInput(e.results[0][0].transcript);
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ---------- LAYOUT ----------
  return (
    <div className="bg-black text-white min-h-screen flex flex-col">
      {/* Sticky Top Bar */}
      <header className="sticky top-0 z-30 border-b border-white/10 backdrop-blur bg-black/60">
        <div className="max-w-4xl mx-auto px-3 py-2 flex items-center gap-3">
          <div className="font-bold tracking-tight text-lg">Droxion</div>
          <div className="text-xs text-gray-400">• Lite</div>
          <div className="ml-auto relative flex items-center gap-2">
            {topToolsOpen && (
              <div className="flex gap-4 glass px-2 py-1 rounded text-sm">
                <FaTrash onClick={() => setMessages([])} className="cursor-pointer" title="Clear chat" />
                <FaDownload className="cursor-pointer" title="Download (todo)" />
                <FaMicrophone className="cursor-pointer" onClick={handleMic} title="Voice to text" />
                {voiceMode
                  ? <FaVolumeUp onClick={() => setVoiceMode(false)} title="Voice off" />
                  : <FaVolumeMute onClick={() => setVoiceMode(true)} title="Voice on" />}
                <FaUpload onClick={() => document.getElementById("fileUpload").click()} title="Upload" />
                <FaCamera title="Screenshot (todo)" />
                <input type="file" id="fileUpload" hidden accept="image/*" />
              </div>
            )}
            <FaPlus onClick={() => setTopToolsOpen(!topToolsOpen)} className="cursor-pointer" title="Tools (⌘/Ctrl+K)" />
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="max-w-4xl mx-auto w-full px-3 py-4">
        <div className="space-y-4">
          {messages.map((msg, i) => {
            const isUser = msg.role === "user";
            const hasCards = !!msg.cards?.length;

            return (
              <div key={i} className={`rounded-xl p-4 ${isUser ? "glass-2" : "glass"}`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[11px] uppercase tracking-wider text-gray-400">
                    {isUser ? "You" : "Droxion"}
                  </div>
                  {!isUser && msg.content && (
                    <button
                      onClick={() => copyMessage(i)}
                      className="text-xs text-gray-400 hover:text-white inline-flex items-center gap-1"
                      title="Copy"
                    >
                      <FaRegCopy />
                      {copiedIdx === i ? "Copied" : "Copy"}
                    </button>
                  )}
                </div>

                {msg.content ? (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeRaw]}
                    components={{
                      img: (props) => <img {...props} className="rounded-lg my-2 w-full glass" loading="lazy" onError={(e)=>e.currentTarget.style.display="none"} />,
                      iframe: (props) => (
                        <div className="embed-responsive embed-16by9 rounded overflow-hidden my-2 glass">
                          <iframe {...props} allowFullScreen />
                        </div>
                      ),
                      a: ({node, ...props}) => <a {...props} className="underline decoration-gray-600 hover:text-gray-200" target="_blank" rel="noreferrer" />
                    }}
                  >
                    {msg.content}
                  </ReactMarkdown>
                ) : null}

                {/* Source pills (for web/news cards) */}
                {!isUser && msg.cards?.length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {msg.cards
                      .filter(c => ["web","news","link","wiki","stock","weather"].includes(c.type))
                      .slice(0, 5)
                      .map((c, idx) => (
                        <a key={idx} href={c.url} target="_blank" rel="noreferrer"
                           className="text-[11px] px-2 py-1 rounded-full border border-white/12 bg-white/5 hover:bg-white hover:text-black transition">
                          {(c.source || (c.url ? new URL(c.url).hostname.replace('www.','') : 'source'))}
                        </a>
                      ))}
                  </div>
                ) : null}

                {hasCards && (
                  <div className="mt-3">
                    {renderCards(msg.cards)}
                  </div>
                )}
              </div>
            );
          })}

          {typing && (
            <div className="glass rounded-xl p-4">
              <div className="h-4 w-24 shimmer mb-2" />
              <div className="h-3 w-full shimmer mb-1" />
              <div className="h-3 w-4/5 shimmer mb-1" />
              <div className="h-3 w-3/5 shimmer" />
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
      </div>

      {/* Spacer so content isn't hidden behind the fixed composer */}
      <div style={{ height: "140px" }} />

      {/* Suggestions dropdown */}
      {suggestions.length > 0 && (
        <div className="suggestion-box">
          {suggestions.map((s, i) => (
            <button key={i} className="suggestion" onClick={() => handleSend(s)}>{s}</button>
          ))}
        </div>
      )}

      {/* Bottom composer (sticky) */}
      <div
        className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-black/80 backdrop-blur"
        style={{ paddingBottom: "max(env(safe-area-inset-bottom), 12px)" }}
      >
        <div className="max-w-4xl mx-auto px-3 pt-2">
          <div className="flex items-center gap-2">
            <div className="flex-1 rounded-2xl border border-white/12 bg-white/5 backdrop-blur px-3 py-2 focus-within:border-white/25 transition">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
                rows={1}
                inputMode="text"
                placeholder="Try: google: latest Ahmedabad weather"
                className="w-full bg-transparent outline-none resize-none leading-[1.6] placeholder-white/30"
                aria-label="Type your message"
              />
            </div>
            <button
              onClick={() => handleSend(input)}
              className="shrink-0 h-10 px-4 rounded-2xl bg-white text-black font-semibold hover:bg-gray-200 active:scale-[0.99] transition"
              title="Send"
            >
              ➤
            </button>
          </div>

          {/* Quick style buttons under the composer */}
          <div className="flex gap-2 flex-wrap mt-2">
            {["Cinematic", "Anime", "Futuristic", "Fantasy", "Realistic"].map(s => (
              <button
                key={s}
                onClick={() => handlePromptClick(s)}
                className="px-3 py-1 rounded-full text-sm border border-white/12 bg-white/5 hover:bg-white hover:text-black transition"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default AIChat;