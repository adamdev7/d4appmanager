/** Format a money amount in the store's ISO currency (e.g. CAD, USD). */
export function formatMoney(value: number, currency = "USD"): string {
  const code = (currency || "USD").toUpperCase();
  const amount = Number.isFinite(value) ? value : 0;
  try {
    return new Intl.NumberFormat(undefined, {
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
