import type { MetaCapiEvent } from "@/lib/metaCapiTypes";

export const FUNNEL_EVENT_ORDER = [
  "PageView",
  "ViewContent",
  "Search",
  "AddToCart",
  "InitiateCheckout",
  "AddPaymentInfo",
  "Purchase",
] as const;

/** Inactivity gap that starts a new session for the same visitor. */
const SESSION_GAP_MS = 30 * 60 * 1000;

export type VisitorSession = {
  id: string;
  visitorKey: string | null;
  visitorLabel: string;
  identifiedBy: string;
  device: string | null;
  ip: string | null;
  landingPage: string | null;
  start: number;
  end: number;
  /** Newest first, same as the flat log. */
  events: MetaCapiEvent[];
  countsByType: Array<[string, number]>;
  furthestStage: string | null;
  outcome: { label: string; variant: "success" | "brand" | "muted" | "warning" };
  purchaseValue: string | null;
  topValue: string | null;
  failed: number;
};

function eventTime(ev: MetaCapiEvent): number {
  const raw = ev.sent_at || ev.created_at;
  const t = raw ? Date.parse(raw) : NaN;
  return Number.isNaN(t) ? 0 : t;
}

function stageIndex(name: string): number {
  const i = FUNNEL_EVENT_ORDER.indexOf(name as (typeof FUNNEL_EVENT_ORDER)[number]);
  return i === -1 ? FUNNEL_EVENT_ORDER.length : i;
}

export function describeDevice(ua: string | null | undefined): string | null {
  if (!ua) return null;
  let app: string | null = null;
  if (/Instagram/i.test(ua)) app = "Instagram app";
  else if (/FBAN|FBAV|FB_IAB/i.test(ua)) app = "Facebook app";
  else if (/TikTok|musical_ly/i.test(ua)) app = "TikTok app";

  let browser = "Browser";
  if (/Edg\//.test(ua)) browser = "Edge";
  else if (/OPR\//.test(ua)) browser = "Opera";
  else if (/SamsungBrowser/.test(ua)) browser = "Samsung Internet";
  else if (/CriOS|Chrome\//.test(ua)) browser = "Chrome";
  else if (/FxiOS|Firefox\//.test(ua)) browser = "Firefox";
  else if (/Safari\//.test(ua)) browser = "Safari";

  let os = "";
  if (/iPhone/.test(ua)) os = "iPhone";
  else if (/iPad/.test(ua)) os = "iPad";
  else if (/Android/.test(ua)) os = "Android";
  else if (/Windows/.test(ua)) os = "Windows";
  else if (/Mac OS X|Macintosh/.test(ua)) os = "Mac";
  else if (/Linux/.test(ua)) os = "Linux";

  return [app ?? browser, os].filter(Boolean).join(" · ");
}

export function pageLabel(ev: MetaCapiEvent): string | null {
  if (ev.content_name) return ev.content_name;
  if (!ev.page_url) return null;
  try {
    const u = new URL(ev.page_url);
    return u.pathname === "/" ? "Home" : decodeURIComponent(u.pathname);
  } catch {
    return ev.page_url;
  }
}

function visitorIdentity(key: string | null): { label: string; identifiedBy: string } {
  if (!key) return { label: "Unidentified visitor", identifiedBy: "No cookie or IP logged" };
  const [prefix, hash = ""] = key.split(":");
  const short = hash.slice(0, 4).toUpperCase();
  const identifiedBy =
    prefix === "fbp" ? "Meta browser cookie" : prefix === "ip" ? "IP + device" : "Customer ID";
  return { label: `Visitor ${short}`, identifiedBy };
}

function outcomeFor(stage: string | null, total: number): VisitorSession["outcome"] {
  switch (stage) {
    case "Purchase":
      return { label: "Purchased", variant: "success" };
    case "AddPaymentInfo":
    case "InitiateCheckout":
      return { label: "Started checkout", variant: "brand" };
    case "AddToCart":
      return { label: "Added to cart", variant: "brand" };
    case "ViewContent":
    case "Search":
      return { label: "Browsed products", variant: "muted" };
    default:
      return { label: total <= 1 ? "Bounced" : "Viewed pages", variant: "muted" };
  }
}

function formatMoney(currency: string | null | undefined, value: number): string {
  return `${currency ?? ""} ${Number.isInteger(value) ? value : value.toFixed(2)}`.trim();
}

function buildSession(visitorKey: string | null, asc: MetaCapiEvent[]): VisitorSession {
  const counts = new Map<string, number>();
  let furthest: string | null = null;
  let failed = 0;
  let purchaseTotal = 0;
  let purchaseCurrency: string | null = null;
  let top: { value: number; currency: string | null } | null = null;

  for (const ev of asc) {
    const name = ev.event_name || "Purchase";
    counts.set(name, (counts.get(name) ?? 0) + 1);
    const known = stageIndex(name) < FUNNEL_EVENT_ORDER.length;
    if (known && (furthest === null || stageIndex(name) > stageIndex(furthest))) furthest = name;
    if (ev.status === "failed") failed += 1;
    const v = ev.order_value != null && ev.order_value !== "" ? Number(ev.order_value) : NaN;
    if (!Number.isNaN(v)) {
      if (name === "Purchase") {
        purchaseTotal += v;
        purchaseCurrency = ev.currency;
      }
      if (!top || v > top.value) top = { value: v, currency: ev.currency };
    }
  }

  const withContext = asc.find((e) => e.user_agent || e.client_ip);
  const landing = asc.find((e) => e.page_url);
  const { label, identifiedBy } = visitorIdentity(visitorKey);

  return {
    id: `${visitorKey ?? "unknown"}:${asc[0]?.id ?? ""}`,
    visitorKey,
    visitorLabel: label,
    identifiedBy,
    device: describeDevice(withContext?.user_agent),
    ip: withContext?.client_ip ?? null,
    landingPage: landing ? pageLabel({ ...landing, content_name: null }) : null,
    start: eventTime(asc[0]),
    end: eventTime(asc[asc.length - 1]),
    events: [...asc].reverse(),
    countsByType: [...counts.entries()].sort((a, b) => stageIndex(a[0]) - stageIndex(b[0])),
    furthestStage: furthest,
    outcome: outcomeFor(furthest, asc.length),
    purchaseValue: purchaseTotal > 0 ? formatMoney(purchaseCurrency, purchaseTotal) : null,
    topValue: top ? formatMoney(top.currency, top.value) : null,
    failed,
  };
}

/** Group a flat event log into per-visitor sessions, newest session first. */
export function groupEventsByVisitor(events: MetaCapiEvent[]): VisitorSession[] {
  const byVisitor = new Map<string, MetaCapiEvent[]>();
  for (const ev of events) {
    const key = ev.visitor_key || "";
    const list = byVisitor.get(key);
    if (list) list.push(ev);
    else byVisitor.set(key, [ev]);
  }

  const sessions: VisitorSession[] = [];
  for (const [key, list] of byVisitor) {
    const asc = [...list].sort((a, b) => eventTime(a) - eventTime(b));
    let current: MetaCapiEvent[] = [];
    for (const ev of asc) {
      const last = current[current.length - 1];
      if (last && eventTime(ev) - eventTime(last) > SESSION_GAP_MS) {
        sessions.push(buildSession(key || null, current));
        current = [];
      }
      current.push(ev);
    }
    if (current.length) sessions.push(buildSession(key || null, current));
  }

  return sessions.sort((a, b) => b.end - a.end);
}
