/** User-friendly personalization fields (stored as {{key}} in templates). */

export type PersonalizationField = {
  key: string;
  label: string;
  example: string;
};

export const PERSONALIZATION_FIELDS: PersonalizationField[] = [
  { key: "customer_name", label: "Customer name", example: "Alex Morgan" },
  { key: "order_number", label: "Order number", example: "#1042" },
  { key: "tracking_number", label: "Tracking number", example: "1Z999AA10123456784" },
  { key: "product_name", label: "Product name", example: "Classic Hoodie" },
  { key: "store_name", label: "Store name", example: "Your Store" },
];

const SAMPLE: Record<string, string> = Object.fromEntries(
  PERSONALIZATION_FIELDS.map((f) => [f.key, f.example])
);

const TOKEN_RE = /\{\{\s*([a-z_]+)\s*\}\}/gi;
/** Also match broken single-brace tokens like {customer_name} */
const SINGLE_TOKEN_RE = /\{([a-z_]+)\}/gi;
const FRIENDLY_TOKEN_RE = /\[([^\]]+)\]/g;

const LABEL_TO_KEY = Object.fromEntries(
  PERSONALIZATION_FIELDS.map((f) => [f.label.toLowerCase(), f.key])
);

const KNOWN_KEYS = new Set(PERSONALIZATION_FIELDS.map((f) => f.key));

const P_STYLE =
  'style="margin:0 0 14px;color:#1f2937;font-size:15px;line-height:1.65;"';

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function decodeBasicEntities(value: string): string {
  return value
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
}

function tokenToFriendlyChip(key: string): string {
  const field = PERSONALIZATION_FIELDS.find((f) => f.key === key.toLowerCase());
  return field ? `[${field.label}]` : `[${key}]`;
}

/** Turn {{customer_name}} (or broken {customer_name}) into [Customer name] for the friendly editor. */
export function tokensToFriendly(text: string): string {
  let s = (text || "").replace(TOKEN_RE, (_, key: string) => tokenToFriendlyChip(key));
  s = s.replace(SINGLE_TOKEN_RE, (match, key: string) =>
    KNOWN_KEYS.has(key.toLowerCase()) ? tokenToFriendlyChip(key) : match
  );
  return s;
}

/** Turn [Customer name] back into {{customer_name}} for storage. */
export function friendlyToTokens(text: string): string {
  return (text || "").replace(FRIENDLY_TOKEN_RE, (match, label: string) => {
    const key = LABEL_TO_KEY[label.trim().toLowerCase()];
    return key ? `{{${key}}}` : match;
  });
}

/** Convert stored HTML body into plain editable text (no tags). */
export function htmlToEditableMessage(html: string): string {
  let s = html || "";
  s = s.replace(/<br\s*\/?>/gi, "\n");
  s = s.replace(/<\/p>\s*<p[^>]*>/gi, "\n\n");
  s = s.replace(/<\/?(p|div|span|strong|b|em|i|u)[^>]*>/gi, "");
  s = s.replace(/<\/?[^>]+>/g, "");
  s = decodeBasicEntities(s);
  s = tokensToFriendly(s);
  return s.replace(/\n{3,}/g, "\n\n").trim();
}

/** Convert plain editable text into email-safe HTML paragraphs. */
export function editableMessageToHtml(text: string): string {
  const withTokens = friendlyToTokens(text || "").trim();
  if (!withTokens) {
    return `<p ${P_STYLE}>&nbsp;</p>`;
  }
  const parts = withTokens.split(/\n\n+/).map((p) => p.trim()).filter(Boolean);
  if (!parts.length) {
    return `<p ${P_STYLE}>&nbsp;</p>`;
  }
  return parts
    .map((part) => {
      const html = escapeHtml(part).replace(/\n/g, "<br/>");
      return `<p ${P_STYLE}>${html}</p>`;
    })
    .join("");
}

/** Subject line: HTML-free, friendly tokens for editing. */
export function subjectToEditable(subject: string): string {
  return tokensToFriendly(subject || "").trim();
}

export function editableSubjectToStored(subject: string): string {
  return friendlyToTokens(subject || "").trim();
}

function resolvePreviewValue(key: string, data: Record<string, string>): string {
  return data[key.toLowerCase()] ?? "";
}

/** Render template text with sample / store data for preview (never show raw tokens). */
export function previewWithSamples(text: string, storeName?: string): string {
  const data = { ...SAMPLE, store_name: storeName || SAMPLE.store_name };
  let result = friendlyToTokens(text || "");
  // Correct {{token}} form first
  result = result.replace(TOKEN_RE, (_, key: string) => resolvePreviewValue(key, data));
  // Broken single-brace {token} leftovers
  result = result.replace(SINGLE_TOKEN_RE, (match, key: string) =>
    KNOWN_KEYS.has(key.toLowerCase()) ? resolvePreviewValue(key, data) : match
  );
  return result;
}

/** Insert a friendly personalization chip at the textarea cursor (or append). */
export function insertFieldAtCursor(
  current: string,
  key: string,
  selectionStart: number,
  selectionEnd: number
): { value: string; cursor: number } {
  const field = PERSONALIZATION_FIELDS.find((f) => f.key === key);
  const chip = field ? `[${field.label}]` : `{{${key}}}`;
  const start = Math.max(0, selectionStart);
  const end = Math.max(start, selectionEnd);
  const before = current.slice(0, start);
  const after = current.slice(end);
  const needsSpaceBefore = before.length > 0 && !/\s$/.test(before);
  const needsSpaceAfter = after.length > 0 && !/^\s/.test(after);
  const inserted =
    (needsSpaceBefore ? " " : "") + chip + (needsSpaceAfter ? " " : "");
  const value = before + inserted + after;
  return { value, cursor: before.length + inserted.length };
}

/** @deprecated prefer insertFieldAtCursor — kept for simple append cases */
export function insertField(current: string, key: string): string {
  return insertFieldAtCursor(current, key, current.length, current.length).value;
}

export function eventLabel(
  eventType: string,
  events: Array<{ event_type: string; label: string; description: string }>
): { label: string; description: string } {
  const found = events.find((e) => e.event_type === eventType);
  return {
    label:
      found?.label ??
      eventType
        .replace(/_/g, " ")
        .toLowerCase()
        .replace(/^\w/, (c) => c.toUpperCase()),
    description: found?.description ?? "Automated email",
  };
}
