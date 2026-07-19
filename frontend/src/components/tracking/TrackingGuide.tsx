import { BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";

const STEPS = [
  {
    title: "Shopify sends order & fulfillment webhooks",
    body: "When a customer places an order, App Manager stores the order. When your supplier adds a tracking number in Shopify (fulfillment), we receive fulfillments/create or fulfillments/update.",
  },
  {
    title: "We save tracking in App Manager",
    body: "Order number, customer email, tracking number, and carrier from Shopify are saved automatically — no manual import.",
  },
  {
    title: "Carrier APIs enrich the shipment (optional)",
    body: "If you add 17TRACK and/or YunExpress keys below and turn on auto-enrich, we fetch live status and timeline events as soon as tracking appears in Shopify.",
  },
  {
    title: "Customers track on your Shopify page",
    body: "Your theme page calls our public API with order number + email. They see status (pending / in transit / delivered) and updates.",
  },
];

export function TrackingGuide() {
  const [open, setOpen] = useState(true);

  return (
    <Card padding="lg">
      <CardHeader>
        <button
          type="button"
          className="flex w-full items-start justify-between gap-4 text-left"
          onClick={() => setOpen((v) => !v)}
        >
          <div>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-brand-600 dark:text-brand-400" />
              How this module works
            </CardTitle>
            <CardDescription className="mt-1">
              End-to-end flow from Shopify order → supplier tracking → carrier APIs → customer
              track page.
            </CardDescription>
          </div>
          {open ? (
            <ChevronUp className="h-5 w-5 shrink-0 text-content-muted" />
          ) : (
            <ChevronDown className="h-5 w-5 shrink-0 text-content-muted" />
          )}
        </button>
      </CardHeader>
      {open && (
        <ol className="px-6 pb-6 space-y-4">
          {STEPS.map((step, i) => (
            <li key={step.title} className="flex gap-4">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-500/15 text-sm font-semibold text-brand-600 dark:text-brand-400">
                {i + 1}
              </span>
              <div>
                <p className="font-medium text-content text-sm">{step.title}</p>
                <p className="text-sm text-content-muted mt-1">{step.body}</p>
              </div>
            </li>
          ))}
          <div className="rounded-xl border border-border bg-surface-muted p-4 text-sm text-content-muted">
            <p className="font-medium text-content mb-2">Wiring checklist</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Shopify store connected in App Manager (Settings → Stores)</li>
              <li>Carrier API keys saved below (at least one for live tracking)</li>
              <li>Auto-enrich enabled when supplier adds tracking in Shopify</li>
              <li>Track Your Order page added to Shopify theme (see embed section)</li>
              <li>Test lookup below with a real order number + email</li>
            </ul>
          </div>
        </ol>
      )}
    </Card>
  );
}
