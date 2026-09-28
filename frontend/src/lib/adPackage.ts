import type { AIAdsAdPackage } from "@/lib/aiAdsTypes";

export const AD_LIMITS = {
  primary_text: { limit: 500, ideal: 450 },
  primary_hook: 125,
  headline: { limit: 40, ideal: 27 },
  description: { limit: 30, ideal: 27 },
} as const;

export const META_CTA_OPTIONS = [
  "SHOP_NOW",
  "LEARN_MORE",
  "GET_OFFER",
  "ORDER_NOW",
  "BUY_NOW",
  "SIGN_UP",
  "SUBSCRIBE",
  "CONTACT_US",
  "DOWNLOAD",
  "APPLY_NOW",
  "GET_QUOTE",
  "BOOK_TRAVEL",
] as const;

export function packageHint(pkg?: AIAdsAdPackage | null) {
  if (!pkg) return "";
  if (pkg.status === "READY") return "Ads Manager copy ready";
  if (pkg.status === "GENERATING") return "Writing copy…";
  if (pkg.status === "FAILED") return "Copy failed";
  return "";
}

export function ctaLabel(cta: string) {
  return (cta || "SHOP_NOW")
    .toLowerCase()
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export type CounterTone = "ok" | "warn" | "over";

export function counterTone(length: number, limit: number, ideal?: number): CounterTone {
  if (length > limit) return "over";
  if (length > (ideal ?? Math.floor(limit * 0.9))) return "warn";
  return "ok";
}

function utmParams(pkg: AIAdsAdPackage, overrides: Partial<AIAdsAdPackage["utm"]> = {}) {
  const utm = { ...pkg.utm, ...overrides };
  const params = new URLSearchParams();
  (Object.keys(utm) as (keyof typeof utm)[]).forEach((key) => {
    if (utm[key]) params.set(key, utm[key]);
  });
  return params;
}

export function urlParameters(pkg: AIAdsAdPackage, overrides: Partial<AIAdsAdPackage["utm"]> = {}) {
  return utmParams(pkg, overrides).toString();
}

export function destinationUrl(pkg: AIAdsAdPackage, overrides: Partial<AIAdsAdPackage["utm"]> = {}) {
  if (!pkg.base_url) return "";
  try {
    const url = new URL(pkg.base_url);
    utmParams(pkg, overrides).forEach((value, key) => url.searchParams.set(key, value));
    return url.toString();
  } catch {
    return pkg.base_url;
  }
}

/** Keeps derived tracking fields in sync after an inline edit. */
export function withTracking(pkg: AIAdsAdPackage): AIAdsAdPackage {
  return {
    ...pkg,
    url_parameters: urlParameters(pkg),
    destination_url: destinationUrl(pkg) || null,
  };
}

function pascal(text: string) {
  return text
    .normalize("NFKD")
    .replace(/[^\w\s]/g, " ")
    .split(/[\s_]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join("");
}

/** `[Product]_[Angle]_[Format]_[Date]` with the angle swapped for the variant's angle. */
export function variantAdName(adName: string, label: string, index: number) {
  const parts = adName.split("_");
  const angle = pascal(label) || `V${index + 1}`;
  if (parts.length >= 4) {
    parts[parts.length - 3] = angle;
    return parts.join("_");
  }
  return `${adName}_${angle}`;
}

export function pasteBlock(pkg: AIAdsAdPackage) {
  const lines: string[] = [];
  const section = (title: string) => lines.push("", `=== ${title} ===`);
  lines.push(`AD NAME: ${pkg.ad_name}`);
  section("CREATIVE");
  lines.push("PRIMARY TEXT:", pkg.primary_text, "");
  lines.push(`HEADLINE: ${pkg.headline}`);
  lines.push(`DESCRIPTION: ${pkg.description}`);
  lines.push(`CALL TO ACTION: ${ctaLabel(pkg.cta)} (${pkg.cta})`);
  lines.push(`WEBSITE URL: ${pkg.base_url || ""}`);
  lines.push(`URL PARAMETERS: ${pkg.url_parameters}`);
  if (pkg.display_link) lines.push(`DISPLAY LINK: ${pkg.display_link}`);
  lines.push(`FULL DESTINATION URL: ${pkg.destination_url || ""}`);

  section("A/B VARIANTS");
  pkg.primary_text_variants.forEach((v) => {
    lines.push(`PRIMARY TEXT — ${v.label}:`, v.text, "");
  });
  pkg.headline_variants.forEach((v) => lines.push(`HEADLINE — ${v.label}: ${v.text}`));

  section("CAMPAIGN SETUP");
  lines.push(`Objective: ${pkg.campaign_objective_label} (${pkg.campaign_objective})`);
  lines.push(`Conversion location: ${pkg.conversion_location}`);
  lines.push(`Conversion event: ${pkg.conversion_event}`);
  lines.push(`Special ad category: ${pkg.special_ad_category} (${pkg.special_ad_category_note})`);
  if (pkg.ai_generated !== false) lines.push(`AI disclosure: ${pkg.ai_disclosure_note || "AI-generated creative"}`);
  if (pkg.test_hypothesis) lines.push(`Test: ${pkg.test_hypothesis}${pkg.test_variable ? ` (variable: ${pkg.test_variable})` : ""}`);
  pkg.tracking_notes.forEach((n) => lines.push(`- ${n}`));

  section("AUDIENCE");
  const a = pkg.audience;
  lines.push(`Age: ${a.age_min}–${a.age_max} · Gender: ${a.genders}`);
  if (a.interests.length) lines.push(`Interests: ${a.interests.join(", ")}`);
  if (a.notes) lines.push(a.notes);
  if (a.lookalike_ideas.length) lines.push("Lookalikes:", ...a.lookalike_ideas.map((x) => `- ${x}`));
  if (a.retargeting_ideas.length) lines.push("Retargeting:", ...a.retargeting_ideas.map((x) => `- ${x}`));

  section(`PLACEMENTS (${pkg.aspect_ratio})`);
  pkg.placements.forEach((p) => lines.push(`- ${p}`));
  if (pkg.placement_notes) lines.push(pkg.placement_notes);
  return lines.join("\n").trim();
}

function csvCell(value: string | number | null | undefined) {
  const text = String(value ?? "");
  return `"${text.replace(/"/g, '""')}"`;
}

/** One row per ad (main + one per A/B angle), using Ads Manager bulk-import column names. */
export function packageCsv(pkg: AIAdsAdPackage) {
  const header = [
    "Ad Name",
    "Body",
    "Title",
    "Link Description",
    "Call to Action",
    "Link",
    "URL Tags",
    "Display Link",
    "Angle",
    "Language",
  ];
  const rows: (string | number)[][] = [
    [
      pkg.ad_name,
      pkg.primary_text,
      pkg.headline,
      pkg.description,
      pkg.cta,
      pkg.base_url || "",
      pkg.url_parameters,
      pkg.display_link,
      pkg.angle,
      pkg.language,
    ],
  ];
  pkg.primary_text_variants.forEach((v, i) => {
    const name = variantAdName(pkg.ad_name, v.label, i);
    rows.push([
      name,
      v.text,
      pkg.headline_variants[i]?.text || pkg.headline,
      pkg.description,
      pkg.cta,
      pkg.base_url || "",
      urlParameters(pkg, { utm_content: name }),
      pkg.display_link,
      v.label,
      pkg.language,
    ]);
  });
  return "\ufeff" + [header, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n");
}

export function downloadText(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}

export async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}
