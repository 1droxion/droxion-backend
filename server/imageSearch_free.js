import fetch from "node-fetch";

/** Wikipedia thumbs (no API key needed) */
async function wikiThumbs(q, n = 10) {
  const url = new URL("https://en.wikipedia.org/w/api.php");
  Object.entries({
    action: "query", format: "json", origin: "*",
    prop: "pageimages|info", inprop: "url",
    piprop: "thumbnail", pithumbsize: 800,
    generator: "search", gsrsearch: q, gsrlimit: String(n)
  }).forEach(([k,v]) => url.searchParams.set(k, v));

  const r = await fetch(url);
  if (!r.ok) return [];
  const j = await r.json();
  const pages = Object.values(j?.query?.pages || {});
  return pages
    .map(p => ({
      url: p.thumbnail?.source || p.fullurl,
      thumb: p.thumbnail?.source || p.fullurl,
      title: p.title,
      source: "wikipedia.org",
      pageUrl: p.fullurl
    }))
    .filter(x => x.url);
}

/** Unsplash public fallback */
function unsplashFallback(q, n = 12) {
  const mk = (k) => `https://source.unsplash.com/900x600/?${encodeURIComponent(k)}`;
  const keys = [q, `${q} photo`, `${q} hd`, `${q} wallpaper`];
  const arr = [];
  for (let i = 0; i < n; i++) {
    const k = keys[i % keys.length];
    const u = mk(k);
    arr.push({ url: u, thumb: u, title: k, source: "unsplash.com", pageUrl: `https://unsplash.com/s/photos/${encodeURIComponent(k)}` });
  }
  return arr;
}

export async function imageFreeSearch(q) {
  const wiki = await wikiThumbs(q, 10);
  const more = unsplashFallback(q, 12);
  const images = [...wiki, ...more].slice(0, 24);
  const sources = [
    { title: "wikipedia.org", url: `https://en.wikipedia.org/wiki/${encodeURIComponent(q)}` },
    { title: "unsplash.com",  url: `https://unsplash.com/s/photos/${encodeURIComponent(q)}` }
  ];
  return { images, sources };
}