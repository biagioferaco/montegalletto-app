// Test della logica orari/stato. Esecuzione: node --test tests/schedule.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { computeStatus, parseClosures, romeDate, holidayName, fmtWhen, upcomingClosures } from "../docs/schedule.js";

const HOURS = { feriale: { open: "07:10", close: "19:50" }, festivo: { open: "07:15", close: "20:55" } };
const at = (s) => romeDate(...s.split(/[- :]/).map(Number));
const CLOS = parseClosures([{ start: "2026-11-04T14:00:00+01:00", end: "2026-11-05T17:00:00+01:00", link: "x" }]);

test("aperto in un feriale, chiude alle 19:50", () => {
  const s = computeStatus(at("2026-11-24 10 00"), [], HOURS);
  assert.equal(s.state, "open");
  assert.equal(fmtWhen(s.closesAt, at("2026-11-24 10 00")), "oggi alle 19:50");
});

test("sabato è feriale", () => {
  const s = computeStatus(at("2026-11-28 20 00"), [], HOURS);
  assert.equal(s.state, "closed");
  assert.equal(s.today.festivo, false);
  assert.equal(fmtWhen(s.reopensAt, at("2026-11-28 20 00")), "domani alle 07:15"); // domenica: festivo
});

test("domenica aperto fino alle 20:55", () => {
  const s = computeStatus(at("2026-11-29 20 30"), [], HOURS);
  assert.equal(s.state, "open");
  assert.equal(s.today.festivo, true);
});

test("festività: San Giovanni e Pasquetta", () => {
  assert.match(holidayName(2026, 6, 24), /San Giovanni/);
  assert.equal(holidayName(2026, 4, 6), "Lunedì dell'Angelo");
  assert.equal(holidayName(2027, 3, 29), "Lunedì dell'Angelo");
  assert.equal(holidayName(2026, 11, 24), null);
});

test("chiuso per lavori, riapre alle 17:00 del giorno dopo", () => {
  const now = at("2026-11-04 15 00");
  const s = computeStatus(now, CLOS, HOURS);
  assert.equal(s.state, "suspended");
  assert.equal(fmtWhen(s.reopensAt, now), "domani alle 17:00");
});

test("chiusura anticipata oggi", () => {
  const now = at("2026-11-04 09 00");
  const s = computeStatus(now, CLOS, HOURS);
  assert.equal(s.state, "open");
  assert.equal(s.closesEarly, true);
  assert.equal(fmtWhen(s.closesAt, now), "oggi alle 14:00");
});

test("chiusura che termina di notte: riapre all'orario normale", () => {
  const c = parseClosures([{ start: "2026-11-24T00:00:00+01:00", end: "2026-11-25T00:00:00+01:00" }]);
  const now = at("2026-11-24 12 00");
  const s = computeStatus(now, c, HOURS);
  assert.equal(s.state, "suspended");
  assert.equal(fmtWhen(s.reopensAt, now), "domani alle 07:10");
});

test("sospensione senza data di fine", () => {
  const c = parseClosures([{ start: "2026-11-24T08:00:00+01:00", end: null }]);
  const s = computeStatus(at("2026-11-24 12 00"), c, HOURS);
  assert.equal(s.state, "suspended");
  assert.equal(s.reopensAt, null);
});

test("ora legale: orari corretti in estate", () => {
  const s = computeStatus(at("2026-07-15 07 12"), [], HOURS);
  assert.equal(s.state, "open");
});

test("chiusure passate non sono in elenco", () => {
  assert.equal(upcomingClosures(at("2026-11-24 12 00"), CLOS).length, 0);
});
