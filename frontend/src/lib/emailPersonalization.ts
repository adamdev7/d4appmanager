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

/** Render template text with sample data for preview (no curly braces shown). */
export function previewWithSamples(text: string, storeName?: string): string {
  const data = { ...SAMPLE, store_name: storeName || SAMPLE.store_name };
  return text.replace(TOKEN_RE, (_, key: string) => data[key.toLowerCase()] ?? "");
}

/** Insert a personalization token at the end of text (internal format). */
export function insertField(current: string, key: string): string {
  const token = `{{${key}}}`;
  const trimmed = current.trimEnd();
  if (!trimmed) return token;
  return `${trimmed} ${token}`;
}

export function eventLabel(
  eventType: string,
  events: Array<{ event_type: string; label: string; description: string }>
): { label: string; description: string } {
  const found = events.find((e) => e.event_type === eventType);
  return {
    label: found?.label ?? eventType.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()),
    description: found?.description ?? "Automated email",
  };
}
