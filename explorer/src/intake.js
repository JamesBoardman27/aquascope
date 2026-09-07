// Study's first sentence, read on the reader's device into a brief. Pure
// functions, no DOM: the prompt a small model gets, the JSON schema that
// constrains its reply, and the reader of that reply. Only what the sentence
// states is kept (a decision, the quantities wanted, a return period, drought
// timescales); the Consultant (aquascope.studio.roles.consultant) fills the
// rest with its own rules and asks for what is missing, so a wrong reading
// costs one question, never a wrong number.

export const RETURN_PERIOD_RANGE = [2, 100000];
export const TIMESCALE_RANGE = [1, 60];
const MAX_ITEMS = 6;
const MAX_CHARS = 120;

/** The system prompt: one object, only what the sentence states. */
export function briefPrompt() {
  return [
    "You read one sentence stating a water problem at a place and fill a short form.",
    "Reply with ONE JSON object and nothing else:",
    '{"decision": "<what will be decided with the answer, a few words>",',
    ' "quantities": ["<the numbers wanted, in words>"],',
    ' "return_period": <years, only when the sentence states one>,',
    ' "timescales": [<months, only when the sentence states them>]}',
    "Leave out any field the sentence does not state. Never invent a number.",
  ].join("\n");
}

/** A JSON schema for the reply, so a constrained decoder cannot wander. */
export function briefSchema() {
  return {
    type: "object",
    properties: {
      decision: { type: "string" },
      quantities: { type: "array", items: { type: "string" } },
      return_period: { type: "integer" },
      timescales: { type: "array", items: { type: "integer" } },
    },
  };
}

const inRange = (n, [lo, hi]) => Number.isInteger(n) && n >= lo && n <= hi;
const cleanText = (s) => String(s).trim().slice(0, MAX_CHARS);

/**
 * The model's text as { brief: {decision, quantities}, intake: {return_period,
 * timescales} } with only the fields that are usable, or null when none is.
 * A number outside its range is dropped, never clamped: the Consultant asks.
 */
export function parseBriefReply(text) {
  const raw = String(text || "").trim();
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  let obj;
  try { obj = JSON.parse(raw.slice(start, end + 1)); } catch { return null; }
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return null;
  const brief = {};
  const intake = {};
  if (typeof obj.decision === "string" && obj.decision.trim()) brief.decision = cleanText(obj.decision);
  if (Array.isArray(obj.quantities)) {
    const qs = obj.quantities.filter((q) => typeof q === "string" && q.trim()).map(cleanText).slice(0, MAX_ITEMS);
    if (qs.length) brief.quantities = qs;
  }
  if (inRange(obj.return_period, RETURN_PERIOD_RANGE)) intake.return_period = obj.return_period;
  if (Array.isArray(obj.timescales)) {
    const ts = obj.timescales.filter((t) => inRange(t, TIMESCALE_RANGE)).slice(0, MAX_ITEMS);
    if (ts.length) intake.timescales = ts;
  }
  if (!Object.keys(brief).length && !Object.keys(intake).length) return null;
  return { brief, intake };
}
