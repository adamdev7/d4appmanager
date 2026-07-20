/** Client-side email layout wrappers (mirrors backend layout_presets). */

export type LayoutPresetId = "classic" | "modern" | "bold";

export type LayoutPresetMeta = {
  id: LayoutPresetId;
  name: string;
  description: string;
};

export const LAYOUT_PRESETS: LayoutPresetMeta[] = [
  {
    id: "classic",
    name: "Classic",
    description: "Centered store name, logo in the footer",
  },
  {
    id: "modern",
    name: "Modern",
    description: "Accent stripe, centered name, logo in the footer",
  },
  {
    id: "bold",
    name: "Bold",
    description: "Full-color header, centered name, logo in the footer",
  },
];

export const DEFAULT_THEME_COLOR = "#0d9488";

const BODY_TEXT = "#1f2937";
const FOOTER_TEXT = "#64748b";
const LOGO_MAX_WIDTH = 200;
const LOGO_MAX_HEIGHT = 96;

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Centered footer logo at natural aspect ratio (soft-capped for email clients). */
function logoBlock(
  logoUrl: string | null | undefined,
  storeName = "",
  fallbackColor = BODY_TEXT
): string {
  if (!logoUrl) return "";
  const src = escapeAttr(logoUrl);
  const fallback = escapeAttr(storeName || "Logo");
  const color = escapeAttr(fallbackColor);
  return `<div style="text-align:center;margin:0 0 14px;"><img src="${src}" alt="${fallback}" style="width:auto;height:auto;max-width:${LOGO_MAX_WIDTH}px;max-height:${LOGO_MAX_HEIGHT}px;display:inline-block;border:0;outline:none;" onerror="this.style.display='none';this.nextElementSibling.style.display='block';" /><p style="display:none;margin:0;font-size:16px;font-weight:600;color:${color};font-family:Arial,Helvetica,sans-serif;">${fallback}</p></div>`;
}

function normalizeBody(bodyHtml: string): string {
  const text = (bodyHtml || "").trim();
  if (!text) return `<p style="margin:0;color:${BODY_TEXT};line-height:1.65;">&nbsp;</p>`;
  if (!text.includes("<")) {
    return text
      .split(/\n\n+/)
      .filter(Boolean)
      .map(
        (p) =>
          `<p style="margin:0 0 12px;color:${BODY_TEXT};font-size:15px;line-height:1.65;">${escapeAttr(p).replace(/\n/g, "<br/>")}</p>`
      )
      .join("");
  }
  return `<div style="color:${BODY_TEXT};font-size:15px;line-height:1.65;font-family:Arial,Helvetica,sans-serif;">${text}</div>`;
}

function footerBlock(storeName: string, reason: string, logoHtml = ""): string {
  return `${logoHtml}<p style="margin:0 0 6px;font-size:12px;line-height:1.5;color:${FOOTER_TEXT};text-align:center;font-family:Arial,Helvetica,sans-serif;">${storeName}</p><p style="margin:0;font-size:11px;line-height:1.5;color:${FOOTER_TEXT};text-align:center;font-family:Arial,Helvetica,sans-serif;">${reason}</p>`;
}

export function renderEmailLayout(options: {
  layoutPreset: string;
  bodyHtml: string;
  themeColor: string;
  logoUrl?: string | null;
  storeName: string;
}): string {
  const color = escapeAttr(
    (options.themeColor?.trim() || DEFAULT_THEME_COLOR).startsWith("#")
      ? options.themeColor.trim() || DEFAULT_THEME_COLOR
      : `#${options.themeColor.trim()}`
  );
  const name = escapeAttr(options.storeName || "Your Store");
  const inner = normalizeBody(options.bodyHtml);
  const preset = (options.layoutPreset || "classic").toLowerCase();
  const reason = `This is a transactional message from ${name}. If you have questions, reply to this email.`;
  const logo = logoBlock(options.logoUrl, name);

  if (preset === "modern") {
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"></head><body style="margin:0;padding:0;background:#f3f4f6;color:${BODY_TEXT};font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:4px;overflow:hidden;">
<tr><td style="height:4px;background:${color};font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:28px 36px 12px;text-align:center;">
<p style="margin:0 0 4px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#6b7280;font-family:Arial,Helvetica,sans-serif;">${name}</p>
</td></tr>
<tr><td style="padding:8px 36px 36px;font-family:Arial,Helvetica,sans-serif;color:${BODY_TEXT};">${inner}</td></tr>
<tr><td style="padding:20px 36px 28px;border-top:1px solid #e5e7eb;text-align:center;">
${footerBlock(name, reason, logo)}
</td></tr>
</table></td></tr></table></body></html>`;
  }

  if (preset === "bold") {
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"></head><body style="margin:0;padding:0;background:#111827;color:${BODY_TEXT};font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#111827;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
<tr><td style="background:${color};padding:28px;text-align:center;">
<p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;font-family:Arial,Helvetica,sans-serif;">${name}</p>
</td></tr>
<tr><td style="padding:32px 28px;color:${BODY_TEXT};">${inner}</td></tr>
<tr><td style="padding:20px 28px 28px;background:#f9fafb;text-align:center;">
${footerBlock(name, reason, logo)}
</td></tr>
</table></td></tr></table></body></html>`;
  }

  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light"></head><body style="margin:0;padding:0;background:#f8fafc;color:${BODY_TEXT};font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
<tr><td style="background:${color};padding:18px 24px;text-align:center;">
<p style="margin:0;font-size:16px;font-weight:600;color:#ffffff;">${name}</p>
</td></tr>
<tr><td style="padding:28px 28px;color:${BODY_TEXT};">${inner}</td></tr>
<tr><td style="padding:20px 28px;background:#f1f5f9;border-top:1px solid #e2e8f0;text-align:center;">
${footerBlock(name, reason, logo)}
</td></tr>
</table></td></tr></table></body></html>`;
}
