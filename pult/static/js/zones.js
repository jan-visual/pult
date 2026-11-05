// Pult: překryv rozhraní sociálních sítí přes video (G). Ukazuje, co v aplikaci zakryjí ikony, jméno
// a popisek. Kreslí se v prostoru 1080 × 1920 (telefon), video se do něj vkládá jako v aplikaci.
// Rozložení odpovídá aplikacím v roce 2026 jen přibližně (liší se podle telefonu a verze).

const W = "#fff";
const P = {
  heart: "M12 20.5s-7.6-4.7-9.4-9.3C1.4 8 3.5 4.5 7 4.5c2 0 3.6 1.1 5 2.9 1.4-1.8 3-2.9 5-2.9 3.5 0 5.6 3.5 4.4 6.7C19.6 15.8 12 20.5 12 20.5z",
  bubble: "M20.3 11.6a8.3 8.3 0 1 1-4-7.1 8.3 8.3 0 0 1 4 7.1zM20.3 20.3l-1.6-4.2",
  plane: "M21.5 3.2L10.4 13.5M21.5 3.2l-6.8 17.9-4.3-7.6-7.7-4.4z",
  dots: "M5 12h.01M12 12h.01M19 12h.01",
  bookmark: "M6.5 3.5h11v17l-5.5-4.2-5.5 4.2z",
  share: "M13.5 4.5l7.5 7-7.5 7v-4.3c-5.2 0-8.6 1.6-11 5.3 1-5.2 4.1-10.1 11-11z",
  ttBubble: "M12 3.5c5.2 0 9 3.4 9 7.7s-3.8 7.7-9 7.7c-1 0-2-.1-2.9-.4L4.5 20.5l1.2-3.8C4 15.3 3 13.3 3 11.2 3 6.9 6.8 3.5 12 3.5z",
  thumb: "M7.5 10.5v10H3.5v-10zM7.5 10.5l4.2-7c1.4 0 2.4 1.1 2.4 2.5v3.3h5c1.3 0 2.3 1.2 2 2.5l-1.4 7.5c-.2 1-1.1 1.7-2.1 1.7H7.5",
  remix: "M4 11.5a8 8 0 0 1 13.6-5.7L20 8.2M20 3.5v4.7h-4.7M20 12.5a8 8 0 0 1-13.6 5.7L4 15.8M4 20.5v-4.7h4.7",
  note: "M9 18V5.5l11-2V16M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
  home: "M3.5 10.8L12 3.5l8.5 7.3V20.5h-5.6v-6.2H9.1v6.2H3.5z",
  search: "M10.5 17.5a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM15.6 15.6l5.4 5.4",
  reels: "M4 4h16v16H4zM4 8.5h16M9 4l2.5 4.5M14.5 4L17 8.5M10.5 11.5v6l5-3z",
  bag: "M5 7.5h14l-1.2 13H6.2zM8.5 7.5a3.5 3.5 0 0 1 7 0",
  camera: "M3.5 7.5h4l1.7-2.5h5.6l1.7 2.5h4v12h-17zM12 17a3.7 3.7 0 1 0 0-7.4 3.7 3.7 0 0 0 0 7.4z",
  friends: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5M16 10.5a3 3 0 1 0 0-6M17.5 14.6c2.2.5 3.6 2.3 4 5.4",
  inbox: "M3.5 12.5l2.5-7.5h12l2.5 7.5v7h-17zM3.5 12.5h5l1 2.5h5l1-2.5h5",
  profile: "M12 11.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 20.5c.8-4 4-6 8-6s7.2 2 8 6",
  subs: "M4 6.5h16v12H4zM6.5 3.5h11M10 9.5v6l5-3z",
  live: "M3.5 6.5h17v11h-17zM8 3l4 3.5L16 3",
};

const g = (d, x, y, s = 64, o = {}) => !d ? "" :
  `<g transform="${o.flip ? `translate(${x} ${y}) scale(1 -1) translate(${-x} ${-y}) ` : ""}translate(${x - s / 2} ${y - s / 2}) scale(${s / 24})"><path d="${d}" fill="${o.fill || "none"}" stroke="${o.stroke || W}" stroke-width="${o.sw || 2}" stroke-linecap="round" stroke-linejoin="round"/></g>`;
const t = (txt, x, y, size = 30, o = {}) =>
  `<text x="${x}" y="${y}" font-size="${size}" font-weight="${o.w || 600}" fill="${o.fill || W}" text-anchor="${o.a || "start"}" opacity="${o.op || 1}">${txt}</text>`;
const col = (items, x = 1000) => items.map(([d, y, label, o]) => g(d, x, y, (o && o.s) || 66, o) + (label ? t(label, x, y + 66, 27, { a: "middle" }) : "")).join("");
const nav = (y, items, h = 1920 - y) => `<rect x="0" y="${y}" width="1080" height="${h}" fill="#000" opacity=".92"/>` +
  items.map(([d, label, o], i) => { const x = 108 + i * 216; return g(d, x, y + (label ? 46 : h / 2), (o && o.s) || 54, o) + (label ? t(label, x, y + 104, 22, { a: "middle", w: 500, op: o && o.dim ? 0.7 : 1 }) : ""); }).join("");
const safe = (l, tp, r, b) => `<rect x="${l * 1080}" y="${tp * 1920}" width="${(1 - l - r) * 1080}" height="${(1 - tp - b) * 1920}" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="3" stroke-dasharray="14 12" rx="10"/>`;
const shade = (y, h, up) => `<rect x="0" y="${y}" width="1080" height="${h}" fill="url(#${up ? "gUp" : "gDown"})"/>`;
const defs = `<defs><linearGradient id="gDown" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity=".45"/><stop offset="1" stop-color="#000" stop-opacity="0"/></linearGradient>
  <linearGradient id="gUp" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".6"/></linearGradient>
  <filter id="sh" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000" flood-opacity=".55"/></filter></defs>`;

// Souřadnice podle šablon Guideify (1080 × 1920): telefon z videa 9:16 ořízne 51 px vlevo i vpravo,
// spodní lišta aplikace leží pod videem, ne přes něj.
function reels() {
  return shade(0, 300, false) + shade(1330, 590, true) + `<g filter="url(#sh)">` +
    g("M12 5v14M5 12h14", 120, 192, 62, { sw: 2.2 }) + t("Reels", 520, 210, 54, { a: "middle", w: 800 }) + g("M6 9l6 6 6-6", 628, 196, 38, { sw: 2.6 }) +
    g("M4 7h9M17 7h3M4 17h3M11 17h9M15 4.5v5M9 14.5v5", 960, 192, 58, { sw: 2.2 }) +
    col([[P.heart, 1254, "12,4 tis."], [P.bubble, 1413, "248"], [P.plane, 1572, "1 024"], [P.dots, 1728, "", { sw: 4 }]], 954) +
    `<rect x="920" y="1808" width="68" height="68" rx="14" fill="#444" stroke="#fff" stroke-width="4"/>` +
    `<circle cx="126" cy="1623" r="38" fill="#666" stroke="#fff" stroke-width="3"/>` + t("tvuj_ucet", 190, 1634, 34, { w: 700 }) +
    `<rect x="390" y="1597" width="142" height="52" rx="12" fill="none" stroke="#fff" stroke-width="3"/>` + t("Sledovat", 461, 1633, 27, { a: "middle", w: 700 }) +
    t("Popisek videa, který se tady zkrátí…", 92, 1712, 33, { w: 500 }) + t("Líbí se uživateli kamarad a dalším 25 517", 150, 1778, 27, { w: 500 }) +
    `<circle cx="112" cy="1768" r="15" fill="#888"/>` +
    `<rect x="92" y="1818" width="352" height="60" rx="30" fill="#fff" fill-opacity=".2"/>` + g(P.note, 126, 1848, 30, { sw: 2.4 }) + t("tvuj_ucet · Původní zvuk", 152, 1858, 26, { w: 500 }) +
    `</g>` + safe(0.085, 0.13, 0.17, 0.2);
}

function tiktok() {
  return shade(0, 280, false) + shade(1330, 590, true) + `<g filter="url(#sh)">` +
    g(P.live, 114, 159, 56) + t("Sledování", 438, 176, 36, { a: "middle", op: 0.65 }) + t("Pro tebe", 651, 176, 38, { a: "middle", w: 800 }) +
    `<rect x="613" y="196" width="76" height="6" rx="3" fill="#fff"/>` + g(P.search, 960, 159, 58) +
    `<circle cx="957" cy="1077" r="48" fill="#666" stroke="#fff" stroke-width="4"/><circle cx="957" cy="1131" r="19" fill="#fe2c55"/>` + g("M12 7v10M7 12h10", 957, 1131, 26, { sw: 3.4 }) +
    col([[P.heart, 1248, "48,2 tis.", { fill: W, s: 72 }], [P.ttBubble, 1431, "1 205", { fill: W, s: 68 }], [P.share, 1617, "892", { fill: W, s: 68 }]], 957) +
    `<circle cx="954" cy="1743" r="40" fill="#222" stroke="#555" stroke-width="12"/><circle cx="954" cy="1743" r="12" fill="#888"/>` +
    `<rect x="75" y="1572" width="280" height="64" rx="8" fill="#000" fill-opacity=".45"/><rect x="95" y="1590" width="28" height="28" rx="4" fill="#f5a524"/>` + t("Odkaz nebo efekt", 136, 1615, 27, { w: 600 }) +
    t("tvuj_ucet", 75, 1696, 36, { w: 800 }) + t("Popisek videa #hashtag #fyp", 75, 1764, 32, { w: 500 }) + t("#dalsi #hashtagy", 75, 1814, 32, { w: 500 }) +
    g(P.note, 88, 1866, 30, { sw: 2.4 }) + t("původní zvuk · tvuj_ucet", 118, 1876, 28, { w: 500 }) + `</g>` + safe(0.085, 0.12, 0.17, 0.2);
}

function shorts() {
  return shade(0, 280, false) + shade(1330, 590, true) + `<g filter="url(#sh)">` +
    t("Shorts", 87, 204, 50, { w: 800 }) + g("M4 9.5h3.2L11.5 6v12l-4.3-3.5H4zM15 9.2a4 4 0 0 1 0 5.6M17.6 6.6a7.6 7.6 0 0 1 0 10.8", 729, 186, 56) +
    g(P.search, 849, 186, 56) + g("M12 5h.01M12 12h.01M12 19h.01", 960, 186, 56, { sw: 4 }) +
    col([[P.thumb, 1149, "12 tis.", { s: 62 }], [P.thumb, 1284, "Nelíbí se", { s: 62, flip: 1 }], [P.ttBubble, 1419, "348", { s: 62 }],
      [P.share, 1557, "Sdílet", { s: 62 }], [P.remix, 1692, "Remix", { s: 60 }]], 954) +
    `<rect x="920" y="1811" width="68" height="68" rx="12" fill="#444" stroke="#fff" stroke-width="4"/>` +
    `<circle cx="123" cy="1731" r="34" fill="#666" stroke="#fff" stroke-width="3"/>` + t("@tvuj_kanal", 172, 1742, 31, { w: 700 }) +
    `<rect x="372" y="1703" width="170" height="56" rx="28" fill="#fff"/>` + t("Odebírat", 457, 1741, 27, { a: "middle", w: 700, fill: "#0f0f0f" }) +
    g("M8 5.5v13l10.5-6.5z", 104, 1809, 28, { fill: W }) + t("Název shortu nebo odkaz na video", 140, 1820, 29, { w: 600 }) +
    t("Popisek, který se tady zkrátí…", 92, 1876, 28, { w: 500, op: 0.85 }) + `</g>` + safe(0.085, 0.12, 0.17, 0.17);
}

export const OVERLAYS = [null, { name: "Instagram Reels", draw: reels }, { name: "TikTok", draw: tiktok }, { name: "YouTube Shorts", draw: shorts }];

// v: kde leží video v prostoru překryvu (1080 × 1920). Mimo video je v aplikaci černo, okraje mimo telefon jsou oříznuté.
export function overlaySvg(z, v = { x: 0, y: 0, w: 1080, h: 1920 }) {
  const out = `M-4000 -4000H5080V5920H-4000Z M51 0H1029V1920H51Z`;
  const black = v.x <= 0.5 && v.y <= 0.5 && v.w >= 1079 && v.h >= 1919 ? "" :
    `<path d="M51 0H1029V1920H51Z M${v.x} ${v.y}h${v.w}v${v.h}h${-v.w}Z" fill="#000" fill-rule="evenodd" opacity=".88"/>`;
  return `<svg viewBox="0 0 1080 1920" preserveAspectRatio="none" width="100%" height="100%" overflow="visible" font-family="-apple-system, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif">${defs}` +
    `${black}<path d="${out}" fill="#000" fill-rule="evenodd" opacity=".72"/>${z.draw()}` +
    `<rect x="51" y="0" width="978" height="1920" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2"/></svg>`;
}
