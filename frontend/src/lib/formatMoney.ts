const CURRENCY_LOCALES: Record<string, string> = {
  CAD: "en-CA",
  USD: "en-US",
  GBP: "en-GB",
  EUR: "en-IE",
};

/** Format a money amount in the given ISO currency (e.g. CAD, USD). */
export function formatMoney(value: number, currency = "USD"): string {
  const code = (currency || "USD").toUpperCase();
  const amount = Number.isFinite(value) ? value : 0;
  const locale = CURRENCY_LOCALES[code];
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: code,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    const sign = amount < 0 ? "−" : "";
    return `${sign}${code} ${Math.abs(amount).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
}
