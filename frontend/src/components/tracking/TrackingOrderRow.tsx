import { useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, Package } from "lucide-react";
import type { TrackingOrder } from "@/lib/api";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";

function formatTime(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusBadgeVariant(status: string) {
  if (status === "delivered") return "success" as const;
  if (status === "in_transit") return "brand" as const;
  return "muted" as const;
}

function statusLabel(status: string) {
  if (status === "in_transit") return "On the way";
  if (status === "delivered") return "Delivered";
  return "Preparing";
}

function shopifyFulfillmentLabel(status: string | null | undefined) {
  const value = (status || "").toLowerCase();
  if (value === "fulfilled") return "Shipped";
  if (value === "partial") return "Partially shipped";
  if (value === "restocked") return "Restocked";
  if (value === "unfulfilled" || !value) return "Not shipped yet";
  return value.replace(/_/g, " ");
}

function shopifyPaymentLabel(status: string | null | undefined) {
  const value = (status || "").toLowerCase();
  if (!value) return null;
  if (value === "paid") return "Paid";
  if (value === "pending") return "Payment pending";
  if (value === "refunded") return "Refunded";
  if (value === "partially_refunded") return "Partially refunded";
  if (value === "authorized") return "Authorized";
  return value.replace(/_/g, " ");
}

function shipmentLabel(status: string | null | undefined) {
  const value = (status || "").toLowerCase();
  if (!value) return "Waiting for carrier updates";
  if (value === "in_transit") return "In transit";
  if (value === "out_for_delivery") return "Out for delivery";
  if (value === "delivered") return "Delivered";
  if (value === "confirmed") return "Label confirmed";
  if (value === "failure") return "Delivery issue";
  return value.replace(/_/g, " ");
}

type Props = {
  order: TrackingOrder;
  shopDomain?: string;
};

export function TrackingOrderRow({ order, shopDomain }: Props) {
  const [open, setOpen] = useState(false);
  const payment = shopifyPaymentLabel(order.shopify_financial_status);
  const fulfillment = shopifyFulfillmentLabel(order.shopify_fulfillment_status);
  const items = order.line_items ?? [];
  const fulfillments = order.fulfillments ?? [];
  const timeline = order.timeline ?? [];
  const productSummary =
    items.length === 0
      ? null
      : items.length === 1
        ? items[0].title
        : `${items[0].title} +${items.length - 1} more`;

  const shopifyAdminUrl =
    shopDomain && order.order_number
      ? `https://${shopDomain}/admin/orders?query=${encodeURIComponent(order.order_number)}`
      : null;

  return (
    <li className="border-b border-border last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-6 py-4 flex flex-wrap items-start justify-between gap-3 text-left hover:bg-surface-muted/50 transition-colors"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-content text-sm">{order.order_number}</p>
            {payment && (
              <span className="text-[11px] uppercase tracking-wide text-content-subtle">{payment}</span>
            )}
          </div>
          <p className="text-sm text-content-muted mt-0.5 truncate">
            {order.customer_name ? `${order.customer_name} · ` : ""}
            {order.customer_email}
          </p>
          {productSummary && (
            <p className="text-xs text-content-subtle mt-1 truncate">{productSummary}</p>
          )}
          {order.tracking_number ? (
            <p className="text-xs text-content-subtle mt-1.5 font-mono">
              {order.tracking_number}
              {order.carrier ? ` · ${order.carrier}` : ""}
            </p>
          ) : (
            <p className="text-xs text-content-subtle mt-1.5">No tracking number yet</p>
          )}
        </div>
        <div className="text-right shrink-0 flex flex-col items-end gap-1.5">
          <Badge variant={statusBadgeVariant(order.status)}>{statusLabel(order.status)}</Badge>
          <p className="text-xs text-content-subtle">{fulfillment}</p>
          <p className="text-xs text-content-subtle">{formatTime(order.last_updated_at)}</p>
          <span className="text-content-muted">
            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </span>
        </div>
      </button>

      {open && (
        <div className="px-6 pb-5 space-y-5 bg-surface-muted/30 border-t border-border">
          <div className="grid sm:grid-cols-3 gap-3 pt-4 text-sm">
            <Detail label="Shopify shipping" value={fulfillment} />
            <Detail label="Payment" value={payment || "—"} />
            <Detail label="Order total" value={order.order_total || "—"} />
            <Detail label="Placed" value={formatTime(order.order_placed_at)} />
            <Detail
              label="Customer"
              value={
                order.customer_name
                  ? `${order.customer_name} (${order.customer_email})`
                  : order.customer_email
              }
            />
            <Detail
              label="Last Shopify update"
              value={formatTime(order.last_updated_at)}
            />
          </div>

          {items.length > 0 && (
            <section>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-content-subtle mb-2">
                Products
              </h4>
              <ul className="space-y-2">
                {items.map((item, idx) => (
                  <li
                    key={`${item.title}-${idx}`}
                    className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2"
                  >
                    {item.image_url ? (
                      <img
                        src={item.image_url}
                        alt=""
                        className="h-10 w-10 rounded-md object-cover bg-surface-muted"
                      />
                    ) : (
                      <span className="flex h-10 w-10 items-center justify-center rounded-md bg-surface-muted text-content-subtle">
                        <Package className="h-4 w-4" />
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-content truncate">{item.title}</p>
                      <p className="text-xs text-content-muted">
                        Qty {item.quantity}
                        {item.variant ? ` · ${item.variant}` : ""}
                      </p>
                    </div>
                    {item.price && (
                      <p className="text-sm text-content-muted shrink-0">{item.price}</p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-content-subtle mb-2">
              Shipments from Shopify
            </h4>
            {fulfillments.length === 0 ? (
              <p className="text-sm text-content-muted rounded-lg border border-dashed border-border px-3 py-3">
                Your manufacturer / shipper hasn&apos;t added a tracking number in Shopify yet.
                When they fulfill the order, it will show up here automatically.
              </p>
            ) : (
              <ul className="space-y-3">
                {fulfillments.map((f) => (
                  <li
                    key={f.id}
                    className="rounded-xl border border-border bg-surface p-4 space-y-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium text-content">
                        {f.carrier || "Shipment"}
                      </p>
                      <Badge
                        variant={statusBadgeVariant(
                          f.shipment_status === "delivered"
                            ? "delivered"
                            : f.tracking_number
                              ? "in_transit"
                              : "pending"
                        )}
                      >
                        {shipmentLabel(f.shipment_status)}
                      </Badge>
                    </div>
                    {f.tracking_number ? (
                      <p className="text-sm font-mono text-content">{f.tracking_number}</p>
                    ) : (
                      <p className="text-sm text-content-muted">No tracking number on this shipment</p>
                    )}
                    {f.items && f.items.length > 0 && (
                      <p className="text-xs text-content-muted">{f.items.join(" · ")}</p>
                    )}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-content-subtle">
                      {f.updated_at && <span>Updated {formatTime(f.updated_at)}</span>}
                      {f.created_at && <span>Created {formatTime(f.created_at)}</span>}
                    </div>
                    {f.tracking_url && (
                      <a
                        href={f.tracking_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline"
                      >
                        Open carrier tracking
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {timeline.length > 0 && (
            <section>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-content-subtle mb-2">
                Activity
              </h4>
              <ul className="space-y-2 border-l border-border pl-3">
                {[...timeline].reverse().map((ev, i) => (
                  <li key={`${ev.at}-${i}`} className="text-sm">
                    <p className="text-content">{ev.description}</p>
                    <p className="text-xs text-content-subtle mt-0.5">{formatTime(ev.at)}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {shopifyAdminUrl && (
            <a
              href={shopifyAdminUrl}
              target="_blank"
              rel="noreferrer"
              className={cn(
                "inline-flex items-center gap-1.5 text-sm text-brand-600 hover:underline"
              )}
            >
              View in Shopify
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      )}
    </li>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-content-subtle">{label}</p>
      <p className="text-sm text-content mt-0.5 break-words">{value}</p>
    </div>
  );
}
