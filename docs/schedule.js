// Calcolo dello stato dell'ascensore: orari, festività, chiusure da avvisi AMT.
// Tutti gli orari sono in ora di Genova (Europe/Rome), qualunque sia il fuso del telefono.

export const TZ = "Europe/Rome";

const partsFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23", weekday: "short",
});
const WD = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

/** Componenti di data/ora a Genova per un istante. */
export function romeParts(date) {
  const p = Object.fromEntries(partsFmt.formatToParts(date).map((x) => [x.type, x.value]));
  return { y: +p.year, m: +p.month, d: +p.day, hh: +p.hour, mm: +p.minute, wd: WD[p.weekday] };
}

/** Istante corrispondente a un'ora "di Genova". */
export function romeDate(y, m, d, hh = 0, mm = 0) {
  let t = Date.UTC(y, m - 1, d, hh, mm);
  for (let i = 0; i < 2; i++) {
    const p = romeParts(new Date(t));
    const asUtc = Date.UTC(p.y, p.m - 1, p.d, p.hh, p.mm);
    t += Date.UTC(y, m - 1, d, hh, mm) - asUtc;
  }
  return new Date(t);
}

function addDays(y, m, d, n) {
  const x = new Date(Date.UTC(y, m - 1, d + n));
  return { y: x.getUTCFullYear(), m: x.getUTCMonth() + 1, d: x.getUTCDate() };
}

function easter(y) { // algoritmo di Meeus/Jones/Butcher
  const a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4;
  const f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30, i = Math.floor(c / 4), k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31), day = ((h + l - 7 * m + 114) % 31) + 1;
  return { m: month, d: day };
}

const FIXED = {
  "1-1": "Capodanno", "1-6": "Epifania", "4-25": "Festa della Liberazione",
  "5-1": "Festa del Lavoro", "6-2": "Festa della Repubblica", "6-24": "San Giovanni Battista, patrono di Genova",
  "8-15": "Ferragosto", "11-1": "Ognissanti", "12-8": "Immacolata Concezione",
  "12-25": "Natale", "12-26": "Santo Stefano",
};

export function holidayName(y, m, d) {
  if (FIXED[`${m}-${d}`]) return FIXED[`${m}-${d}`];
  // San Francesco d'Assisi è di nuovo festa nazionale dal 2026
  if (m === 10 && d === 4 && y >= 2026) return "San Francesco d'Assisi";
  const e = easter(y);
  if (m === e.m && d === e.d) return "Pasqua";
  const pm = addDays(y, e.m, e.d, 1);
  if (m === pm.m && d === pm.d) return "Lunedì dell'Angelo";
  return null;
}

/** Tipo di giornata: i feriali includono il sabato, festivi = domeniche e festività. */
export function dayInfo(y, m, d, hours) {
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  const holiday = holidayName(y, m, d);
  const festivo = wd === 0 || holiday !== null;
  const h = festivo ? hours.festivo : hours.feriale;
  const [oh, om] = h.open.split(":").map(Number);
  const [ch, cm] = h.close.split(":").map(Number);
  return {
    y, m, d, festivo, holiday, sunday: wd === 0,
    open: romeDate(y, m, d, oh, om),
    close: romeDate(y, m, d, ch, cm),
    hours: h,
  };
}

export function parseClosures(list) {
  return (list || []).map((c) => ({
    start: new Date(c.start),
    end: c.end ? new Date(c.end) : null,
    link: c.link,
  }));
}

function closureAt(t, closures) {
  return closures.find((c) => c.start <= t && (c.end === null || t < c.end)) || null;
}

/** Primo istante >= from in cui l'ascensore è in servizio. null = data non comunicata. */
export function nextOpening(from, closures, hours, maxDays = 120) {
  const p = romeParts(from);
  for (let i = 0; i < maxDays; i++) {
    const day = addDays(p.y, p.m, p.d, i);
    const info = dayInfo(day.y, day.m, day.d, hours);
    let t = from > info.open ? from : info.open;
    while (t < info.close) {
      const c = closureAt(t, closures);
      if (!c) return t;
      if (c.end === null) return null;
      t = c.end;
    }
  }
  return null;
}

/**
 * Stato in un dato istante.
 * state: "open" | "closed" (fuori orario) | "suspended" (chiuso per avviso AMT)
 */
export function computeStatus(now, closures, hours) {
  const p = romeParts(now);
  const today = dayInfo(p.y, p.m, p.d, hours);
  const active = closureAt(now, closures);

  if (active) {
    const from = active.end;
    return {
      state: "suspended", today, closure: active,
      reopensAt: from === null ? null : nextOpening(from, closures, hours),
    };
  }
  if (now >= today.open && now < today.close) {
    const nextClosure = closures
      .filter((c) => c.start > now && c.start < today.close)
      .sort((a, b) => a.start - b.start)[0];
    return {
      state: "open", today,
      closesAt: nextClosure ? nextClosure.start : today.close,
      closesEarly: Boolean(nextClosure),
    };
  }
  return { state: "closed", today, reopensAt: nextOpening(now, closures, hours) };
}

/** Chiusure che riguardano oggi o il futuro, in ordine. */
export function upcomingClosures(now, closures) {
  return closures.filter((c) => c.end === null || c.end > now).sort((a, b) => a.start - b.start);
}

// ---------------------------------------------------------------- formattazione

const dayFmt = new Intl.DateTimeFormat("it-IT", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
const timeFmt = new Intl.DateTimeFormat("it-IT", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });

export const fmtTime = (d) => timeFmt.format(d);

/** "oggi alle 07:10", "domani alle 07:15", "venerdì 6 novembre alle 07:10" */
export function fmtWhen(d, now) {
  const a = romeParts(d), b = romeParts(now);
  const diff = Math.round((Date.UTC(a.y, a.m - 1, a.d) - Date.UTC(b.y, b.m - 1, b.d)) / 86400000);
  const day = diff === 0 ? "oggi" : diff === 1 ? "domani" : dayFmt.format(d);
  return `${day} alle ${fmtTime(d)}`;
}

export function fmtDay(d) {
  return dayFmt.format(d);
}
