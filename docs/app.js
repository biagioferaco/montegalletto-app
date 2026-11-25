import {
  computeStatus, parseClosures, upcomingClosures, romeParts, dayInfo,
  fmtWhen, fmtTime, fmtDay,
} from "./schedule.js";

const $ = (s) => document.querySelector(s);
const STALE_MIN = 90;     // oltre questo, avvisa che i dati AMT potrebbero non essere aggiornati
let data = null;

function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  for (const c of children) n.append(c);
  return n;
}
const link = (href, text) => el("a", { href, target: "_blank", rel: "noopener" }, text);

function describeClosure(c, now) {
  const midnight = (d) => { const p = romeParts(d); return p.hh === 0 && p.mm === 0; };
  const from = midnight(c.start) ? fmtDay(c.start) : fmtWhen(c.start, now);
  if (c.end === null) return `Da ${from}, fino a nuova comunicazione`;
  if (midnight(c.end)) {
    const last = new Date(c.end.getTime() - 3600_000);
    if (midnight(c.start)) {
      return fmtDay(last) === fmtDay(c.start)
        ? `${cap(fmtDay(c.start))}, tutto il giorno`
        : `Da ${fmtDay(c.start)} a ${fmtDay(last)} compreso`;
    }
    return `Da ${from} fino a fine servizio di ${fmtDay(last)}`;
  }
  return `Da ${from} fino a ${fmtWhen(c.end, now)}`;
}
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function render() {
  if (!data) return;
  const now = new Date();
  const hours = data.hours;
  const closures = parseClosures(data.closures);
  const s = computeStatus(now, closures, hours);
  const box = $("#status");
  box.dataset.state = s.state;
  const [label, detail, extra] = [".state-label", ".state-detail", ".state-extra"].map((q) => box.querySelector(q));
  extra.replaceChildren();

  if (s.state === "open") {
    label.textContent = "Aperto";
    detail.textContent = s.closesEarly
      ? `Chiude in anticipo ${fmtWhen(s.closesAt, now)} per un avviso AMT`
      : `Chiude ${fmtWhen(s.closesAt, now)}`;
  } else if (s.state === "suspended") {
    label.textContent = "Chiuso per avviso AMT";
    detail.textContent = s.reopensAt ? `Riapre ${fmtWhen(s.reopensAt, now)}` : "Data di riapertura non ancora comunicata";
    if (s.closure.link) extra.append(link(s.closure.link, "Leggi l'avviso"));
  } else {
    label.textContent = "Chiuso";
    detail.textContent = s.reopensAt ? `Riapre ${fmtWhen(s.reopensAt, now)}` : "Data di riapertura non comunicata";
    if (s.reopensAt) {
      const r = romeParts(s.reopensAt);
      const info = dayInfo(r.y, r.m, r.d, hours);
      const normal = Math.abs(s.reopensAt - info.open) < 60_000;
      if (!normal) extra.textContent = "Riapertura spostata da un avviso AMT.";
    }
  }

  // Orari di oggi
  const t = s.today;
  const kind = t.holiday ? `festivo (${t.holiday})` : t.sunday ? "festivo (domenica)" : "feriale";
  $("#today").textContent = `Oggi è un giorno ${kind}: ${fmtTime(t.open)}–${fmtTime(t.close)}`;
  $("#h-feriale").textContent = `${hours.feriale.open.replace(":", ".")} – ${hours.feriale.close.replace(":", ".")}`;
  $("#h-festivo").textContent = `${hours.festivo.open.replace(":", ".")} – ${hours.festivo.close.replace(":", ".")}`;
  $("#h-feriale").parentElement.classList.toggle("current", !t.festivo);
  $("#h-festivo").parentElement.classList.toggle("current", t.festivo);
  if (hours.source) $("#hours-src").href = hours.source;

  // Chiusure in programma
  const up = upcomingClosures(now, closures);
  $("#upcoming").hidden = up.length === 0;
  $("#upcoming ul").replaceChildren(...up.map((c) => {
    const li = el("li", {}, describeClosure(c, now));
    if (c.link) li.append(" · ", link(c.link, "avviso"));
    return li;
  }));

  // Avvisi da controllare a mano
  const review = data.needs_review || [];
  $("#review").hidden = review.length === 0;
  $("#review ul").replaceChildren(...review.map((r) => el("li", {}, link(r.link, r.title))));

  // Notizie
  const [latest, ...older] = data.news || [];
  const news = $("#news");
  if (latest) {
    const pub = new Date(latest.published), mod = new Date(latest.modified);
    let meta = `Pubblicato ${fmtDay(pub)} ${romeParts(pub).y}`;
    if (mod - pub > 3600_000) meta += ` · aggiornato ${fmtWhen(mod, now)}`;
    news.replaceChildren(
      el("h3", {}, link(latest.link, latest.title)),
      el("p", { class: "meta" }, meta),
      el("p", {}, latest.text),
    );
  } else {
    news.replaceChildren(el("p", { class: "muted" }, "Nessun avviso trovato."));
  }
  $("#older").hidden = older.length === 0;
  $(".older").replaceChildren(...older.map((n) =>
    el("li", {}, link(n.link, n.title), el("span", { class: "muted" }, ` · ${fmtDay(new Date(n.published))} ${romeParts(new Date(n.published)).y}`))));

  // Freschezza dei dati
  const gen = new Date(data.generated_at);
  const ageMin = Math.round((now - gen) / 60000);
  $("#freshness").textContent = ageMin > STALE_MIN
    ? `Attenzione: avvisi AMT controllati l'ultima volta ${fmtWhen(gen, now)}. Potrebbero esserci novità.`
    : `Avvisi AMT controllati ${ageMin < 2 ? "adesso" : `${ageMin} minuti fa`}.`;
}

async function load() {
  try {
    const r = await fetch(`status.json?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    data = await r.json();
    render();
  } catch (e) {
    if (!data) {
      const box = $("#status");
      box.dataset.state = "error";
      box.querySelector(".state-label").textContent = "Dati non disponibili";
      box.querySelector(".state-detail").textContent = "Controlla la connessione e riprova.";
    }
  }
}

load();
setInterval(render, 30_000);
setInterval(load, 5 * 60_000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js");
