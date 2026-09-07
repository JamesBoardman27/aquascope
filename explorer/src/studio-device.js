// The model on the reader's device as the Methodologist and the Author.
// Pure functions, no DOM and no model of their own: each takes the context
// the worker's engine would send to its model (with the system prompt under
// `system`), the exported prompts when the page has them (their schemas), and
// a `generate` function ({system, prompt, schema, temperature, timeoutMs,
// onProgress}) -> text, which is local-model.js's generateJsonLocally on the
// page and a fake under node. What the model writes is never trusted here:
// the plan goes to the engine's validator (the tree stands when it fails),
// the prose to the Critic's checks (a sentence with a number the results do
// not carry is dropped), and the page says who wrote what.

export const CALL_TIMEOUT_MS = 25000;   // per call, as Ask's on-device brief
export const MAX_AUTHOR_CALLS = 4;      // summary and recommendations first, then per step
export const FAST_CALL_MS = 8000;       // a first call quicker than this earns the per-step calls
export const CONTEXT_BUDGET = 14000;    // characters of context a small model reads in one go

// ── the reply ───────────────────────────────────────────────────────────────

/** The first JSON object in a reply: the whole text, a fenced block, or the outermost braces; else null. */
export function parseJsonReply(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  const tries = [raw];
  const fence = raw.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
  if (fence) tries.push(fence[1]);
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start >= 0 && end > start) tries.push(raw.slice(start, end + 1));
  for (const t of tries) {
    try {
      const obj = JSON.parse(t);
      if (obj && typeof obj === "object" && !Array.isArray(obj)) return obj;
    } catch { /* next */ }
  }
  return null;
}

// ── the context, cut to size ────────────────────────────────────────────────

const firstSentence = (s, n = 90) => String(s || "").split(/(?<=[.!?])\s/)[0].slice(0, n);

function slimCatalogue(entries) {
  if (!Array.isArray(entries)) return entries;
  return entries.map((e) => {
    if (!e || typeof e !== "object") return e;
    const args = e.arguments && typeof e.arguments === "object" && !Array.isArray(e.arguments)
      ? Object.keys(e.arguments) : e.arguments;
    const out = { id: e.id, kind: e.kind, purpose: firstSentence(e.purpose || e.description) };
    if (args) out.arguments = args;
    if (e.required) out.required = e.required;
    if (e.methods) out.methods = e.methods;
    if (e.gates) out.gates = e.gates;
    if (e.yields) out.yields = e.yields;
    return out;
  });
}

const size = (o) => JSON.stringify(o).length;

// A value with its long lists and strings cut, the way the engine's own
// compact() keeps a result readable: lists to `maxList` items, strings to
// `maxStr` characters, nested all the way down.
export function shrink(value, { maxList = 12, maxStr = 160 } = {}) {
  if (Array.isArray(value)) return value.slice(0, maxList).map((v) => shrink(v, { maxList, maxStr }));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, shrink(v, { maxList, maxStr })]));
  }
  if (typeof value === "string" && value.length > maxStr) return `${value.slice(0, maxStr)}…`;
  return value;
}

/**
 * The context without its system prompt, trimmed until it fits `budget`
 * characters: the catalogue's entries to their essentials, the gate
 * vocabulary to names, the inventory to its first rows, the results to
 * their first items, then the catalogue to the tools the exemplar uses plus
 * a dozen, and last a hard cut. The exemplar (the tree's own plan) and the
 * brief are never touched.
 */
export function compactContext(context, budget = CONTEXT_BUDGET) {
  const ctx = { ...(context || {}) };
  delete ctx.system;
  if (size(ctx) <= budget) return ctx;
  if (ctx.catalogue) ctx.catalogue = slimCatalogue(ctx.catalogue);
  if (size(ctx) <= budget) return ctx;
  if (ctx.gates && typeof ctx.gates === "object" && !Array.isArray(ctx.gates)) ctx.gates = Object.keys(ctx.gates);
  if (size(ctx) <= budget) return ctx;
  if (ctx.inventory && Array.isArray(ctx.inventory.datasets)) {
    ctx.inventory = { ...ctx.inventory, datasets: ctx.inventory.datasets.slice(0, 8) };
  }
  if (Array.isArray(ctx.inventory)) ctx.inventory = ctx.inventory.slice(0, 8);
  if (size(ctx) <= budget) return ctx;
  if (Array.isArray(ctx.steps)) ctx.steps = ctx.steps.map((s) => (s && typeof s === "object" ? shrink(s) : s));
  if (size(ctx) <= budget) return ctx;
  if (Array.isArray(ctx.catalogue)) {
    const used = new Set(((ctx.exemplar || {}).steps || []).map((s) => s && s.tool));
    const keep = ctx.catalogue.filter((e) => e && used.has(e.id));
    for (const e of ctx.catalogue) {
      if (keep.length >= used.size + 12) break;
      if (e && !used.has(e.id)) keep.push(e);
    }
    ctx.catalogue = keep;
  }
  if (size(ctx) <= budget) return ctx;
  return { truncated: true, text: JSON.stringify(ctx).slice(0, budget) };
}

// ── schemas, when the export has none ───────────────────────────────────────

export const PLAN_SCHEMA = {
  type: "object",
  properties: {
    objective: { type: "string" },
    decision: { type: "string" },
    methodology: { type: "array", items: { type: "string" } },
    steps: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string" },
          tool: { type: "string" },
          arguments: { type: "object" },
          rationale: { type: "string" },
          method: { type: "string" },
          expects: { type: "array", items: { type: "object" } },
          depends_on: { type: "array", items: { type: "string" } },
        },
        required: ["id", "tool", "arguments"],
      },
    },
    assumptions: { type: "array", items: { type: "string" } },
    limitations_expected: { type: "array", items: { type: "string" } },
  },
  required: ["steps"],
};

export const SECTIONS_SCHEMA = {
  type: "object",
  properties: { sections: { type: "object", additionalProperties: { type: "string" } } },
  required: ["sections"],
};

const schemaOf = (prompts, name, fallback) => (prompts && prompts.schemas && prompts.schemas[name]) || fallback;

// ── the Methodologist ───────────────────────────────────────────────────────

/**
 * One call: the methodologist context as the prompt, the exported (or the
 * fallback) plan schema. Returns { plan, error, ms }: the plan is the reply
 * with `source: "device"`, or null with the reason.
 */
export async function planOnDevice({ context, prompts = null, generate, timeoutMs = CALL_TIMEOUT_MS,
                                     onProgress = () => {} } = {}) {
  const system = (context && context.system) || (prompts && prompts.methodologist) || null;
  if (!system) return { plan: null, error: "no prompt for the Methodologist", ms: 0 };
  const t0 = Date.now();
  let text;
  try {
    text = await generate({
      system, prompt: JSON.stringify(compactContext(context)), schema: schemaOf(prompts, "plan", PLAN_SCHEMA),
      temperature: 0.1, timeoutMs, onProgress,
    });
  } catch (err) {
    return { plan: null, error: (err && err.message) || "the device model failed", ms: Date.now() - t0 };
  }
  const ms = Date.now() - t0;
  const obj = parseJsonReply(text);
  const plan = obj && !Array.isArray(obj.steps) && obj.plan && Array.isArray(obj.plan.steps) ? obj.plan : obj;
  if (!plan || !Array.isArray(plan.steps) || !plan.steps.length) {
    return { plan: null, error: obj ? "the reply had no steps" : "the reply was not JSON", ms };
  }
  return { plan: { ...plan, source: "device" }, error: null, ms };
}

// ── the Author ──────────────────────────────────────────────────────────────

const isProse = (v) => typeof v === "string" && v.trim().length > 0;

function sectionsIn(obj, wanted) {
  const out = {};
  if (!obj) return out;
  const src = obj.sections && typeof obj.sections === "object" ? obj.sections : obj;
  for (const id of wanted) if (isProse(src[id])) out[id] = src[id].trim();
  return out;
}

/** The ids of the steps whose results the Author may narrate, in order, from the author context. */
export function resultStepIds(context) {
  const steps = (context && Array.isArray(context.steps)) ? context.steps : [];
  return steps.filter((s) => s && s.id && s.ok !== false && s.result).map((s) => String(s.id));
}

/**
 * The prose, in at most `maxCalls` calls: the summary and the recommendations
 * first; then, when that first call came back within `fastMs`, one call per
 * result step (the context cut to that step) until the cap. Returns
 * { sections, calls, ms, error }; sections is empty with the reason when
 * nothing usable came back.
 */
export async function narrateOnDevice({ context, prompts = null, generate, timeoutMs = CALL_TIMEOUT_MS,
                                        maxCalls = MAX_AUTHOR_CALLS, fastMs = FAST_CALL_MS,
                                        onProgress = () => {} } = {}) {
  const system = (context && context.system) || (prompts && prompts.author) || null;
  if (!system) return { sections: {}, calls: 0, ms: 0, error: "no prompt for the Author" };
  const schema = schemaOf(prompts, "sections", SECTIONS_SCHEMA);
  const base = compactContext(context);
  const sections = {};
  let calls = 0;
  const t0 = Date.now();
  const ask = async (ids, ctx) => {
    calls += 1;
    const prompt = `${JSON.stringify({ ...ctx, write: ids })}\nWrite only these sections: ${ids.join(", ")}.`;
    const started = Date.now();
    const text = await generate({ system, prompt, schema, temperature: 0.2, timeoutMs, onProgress });
    Object.assign(sections, sectionsIn(parseJsonReply(text), ids));
    return Date.now() - started;
  };
  let first;
  try {
    first = await ask(["summary", "recommendations"], base);
  } catch (err) {
    return { sections: {}, calls, ms: Date.now() - t0, error: (err && err.message) || "the device model failed" };
  }
  if (!Object.keys(sections).length) {
    return { sections: {}, calls, ms: Date.now() - t0, error: "the reply carried no section" };
  }
  if (first < fastMs) {
    for (const id of resultStepIds(context).slice(0, Math.max(0, maxCalls - 1))) {
      const step = (context.steps || []).find((s) => String(s.id) === id);
      const ctx = { ...base, steps: [step] };
      try {
        await ask([`results-${id}`], ctx);
      } catch (err) {
        onProgress(`the device model stopped at step ${id}: ${(err && err.message) || "failed"}`);
        break;
      }
    }
  }
  return { sections, calls, ms: Date.now() - t0, error: null };
}

// ── the words on the card ───────────────────────────────────────────────────

/** Who planned: from the approve reply's plan_used and plan_errors, or from a plan's author field. */
export function planLine({ used = null, errors = [], author = null, model = "this device" } = {}) {
  if (used === "proposed" || used === "device") return `planned on this device with ${model}`;
  if (used === "tree" && errors && errors.length) {
    return `the playbook's plan (the device model's plan did not pass the validator: ${errors[0]})`;
  }
  if (author === "device") return `planned on this device with ${model}`;
  if (author === "methodologist") return "planned by the model";
  return "the playbook's plan";
}

/** Who wrote: from the narrate reply's written_by and dropped, or the reason the template stands. */
export function proseLine({ writtenBy = null, dropped = 0, model = "this device", failed = null } = {}) {
  if (failed) return `the template text stands; ${failed}`;
  if (writtenBy !== "device" && writtenBy !== "proposed") return null;
  const n = Array.isArray(dropped) ? dropped.length : Number(dropped) || 0;
  const tail = n === 0 ? "nothing dropped by the checks" : `${n} sentence${n === 1 ? "" : "s"} dropped by the checks`;
  return `written on this device with ${model}; ${tail}`;
}
