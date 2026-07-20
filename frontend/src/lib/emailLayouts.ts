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
    description: "Clean header bar, centered logo, simple body",
  },
  {
    id: "modern",
    name: "Modern",
    description: "Accent stripe, left-aligned logo, spacious layout",
  },
  {
    id: "bold",
    name: "Bold",
    description: "Full-color header with strong brand presence",
  },
];

export const DEFAULT_THEME_COLOR = "#0d9488";

function escapeAttr(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function logoBlock(logoUrl: string | null | undefined, maxHeight = 48, align = "center"): string {
  if (!logoUrl) return "";
  const src = escapeAttr(logoUrl);
  return `<div style="text-align:${align};margin:0 0 20px;"><img src="${src}" alt="Logo" style="max-height:${maxHeight}px;max-width:220px;height:auto;display:inline-block;" /></div>`;
}

function normalizeBody(bodyHtml: string): string {
  const text = (bodyHtml || "").trim();
  if (!text) return '<p style="margin:0;color:#374151;line-height:1.6;">&nbsp;</p>';
  if (!text.includes("<")) {
    return text
      .split(/\n\n+/)
      .filter(Boolean)
      .map(
        (p) =>
          `<p style="margin:0 0 12px;color:#374151;font-size:15px;line-height:1.6;">${escapeAttr(p).replace(/\n/g, "<br/>")}</p>`
      )
      .join("");
  }
  return text;
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

  if (preset === "modern") {
    const logo = logoBlock(options.logoUrl, 44, "left");
    return `<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f3f4f6;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:4px;overflow:hidden;">
<tr><td style="height:4px;background:${color};font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:32px 36px 12px;">${logo}
<p style="margin:0 0 4px;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#9ca3af;font-family:Arial,Helvetica,sans-serif;">${name}</p>
</td></tr>
<tr><td style="padding:8px 36px 36px;font-family:Arial,Helvetica,sans-serif;">${inner}</td></tr>
<tr><td style="padding:16px 36px 28px;border-top:1px solid #e5e7eb;">
<p style="margin:0;font-size:12px;color:#9ca3af;font-family:Arial,Helvetica,sans-serif;">Sent by ${name}</p>
</td></tr>
</table></td></tr></table></body></html>`;
  }

  if (preset === "bold") {
    const logo = logoBlock(options.logoUrl, 52, "center");
    const headerInner =
      logo ||
      `<p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;font-family:Arial,Helvetica,sans-serif;">${name}</p>`;
    return `<!DOCTYPE html><html><body style="margin:0;padding:0;background:#111827;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#111827;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;">
<tr><td style="background:${color};padding:36px 28px;text-align:center;">${headerInner}</td></tr>
<tr><td style="padding:32px 28px;">${inner}</td></tr>
<tr><td style="padding:18px 28px 28px;background:#f9fafb;">
<p style="margin:0;font-size:12px;color:#6b7280;text-align:center;">© ${name}</p>
</td></tr>
</table></td></tr></table></body></html>`;
  }

  const logo = logoBlock(options.logoUrl, 48, "center");
  return `<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
<tr><td style="background:${color};padding:18px 24px;text-align:center;">
<p style="margin:0;font-size:16px;font-weight:600;color:#ffffff;">${name}</p>
</td></tr>
<tr><td style="padding:28px 28px 8px;">${logo}</td></tr>
<tr><td style="padding:0 28px 28px;">${inner}</td></tr>
<tr><td style="padding:14px 28px;background:#f1f5f9;border-top:1px solid #e2e8f0;">
<p style="margin:0;font-size:12px;color:#64748b;text-align:center;">${name}</p>
</td></tr>
</table></td></tr></table></body></html>`;
}
