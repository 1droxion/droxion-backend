// server/imageSearch_free.js
// Simple, no-API-key image search helper.
// 1) Try Lexica (public JSON API).
// 2) Fall back to Unsplash Source (randomized) so you always get images.

const LEXICA = (q) => `https://lexica.art/api/v1/search?q=${encodeURIComponent(q)}`;

// Build N distinct Unsplash Source URLs (no key, cache-busting with sig)
function buildUnsplashFallback(q, n = 10) {
  const base = `https://source.unsplash.com/900x600/?${encodeURIComponent(q)}`;
  const alts = [
    q,
    `${q} photo`,
    `${q} image`,
    `${q} wallpaper`,
    `${q} aesthetic`,
    `${q} hd`,
    `${q} landscape`,
    `${q} portrait`,
    `${q} macro`,
    `${q} art`
  ];
  const out = [];
  for (let i = 0; i < n; i++) {
    const kw = alts[i % alts.length];
    out.push(`https://source.unsplash.com/900x600/?${encodeURIComponent(kw)}&sig=${i + 13}`);
  }
  return out;
}

// Normalize into { url, pageUrl, title, source }
function normalizeLexica(images = [], q = "") {
  return images
    .map((im) => {
      const url = im?.src || im?.imageUrl || im?.jpeg || im?.png;
      if (!url) return null;
      return {
        url,
        pageUrl: im?.id ? `https://lexica.art/prompt/${im.id}` : `https://lexica.art/?q=${encodeURIComponent(q)}`,
        title: im?.prompt || q,
        source: "lexica.art",
      };
    })
    .filter(Boolean);
}

export default async function searchImagesFree(query = "") {
  const q = String(query || "").trim() || "image";

  // ---------- 1) Try Lexica ----------
  try {
    const r = await fetch(LEXICA(q), { method: "GET", headers: { "accept": "application/json" } });
    if (r.ok) {
      const data = await r.json();
      if (data && Array.isArray(data.images) && data.images.length) {
        const items = normalizeLexica(data.images, q);
        if (items.length) {
          return {
            images: items,
            sources: [
              { title: "Lexica", url: `https://lexica.art/?q=${encodeURIComponent(q)}` },
              { title: "Google Images", url: `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(q)}` },
              { title: "Bing Images", url: `https://www.bing.com/images/search?q=${encodeURIComponent(q)}` },
              { title: "Unsplash", url: `https://unsplash.com/s/photos/${encodeURIComponent(q)}` },
            ],
          };
        }
      }
    }
  } catch (e) {
    // non-fatal; we’ll fall back
    console.error("Lexica fetch failed:", e?.message || e);
  }

  // ---------- 2) Unsplash Source fallback (no JSON, just direct images) ----------
  const uns = buildUnsplashFallback(q, 12).map((u) => ({
    url: u,
    pageUrl: `https://unsplash.com/s/photos/${encodeURIComponent(q)}`,
    title: q,
    source: "unsplash.com",
  }));

  return {
    images: uns,
    sources: [
      { title: "Google Images", url: `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(q)}` },
      { title: "Bing Images", url: `https://www.bing.com/images/search?q=${encodeURIComponent(q)}` },
      { title: "Unsplash", url: `https://unsplash.com/s/photos/${encodeURIComponent(q)}` },
      { title: "Lexica", url: `https://lexica.art/?q=${encodeURIComponent(q)}` },
    ],
  };
}