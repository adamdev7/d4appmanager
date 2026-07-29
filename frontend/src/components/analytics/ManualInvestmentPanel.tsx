import { useCallback, useEffect, useState } from "react";
import { Landmark, Pencil, Plus, Trash2 } from "lucide-react";
import { api, type ManualInvestment } from "@/lib/api";
import { formatMoney } from "@/lib/formatMoney";
import { Card, CardDescription, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";

type Props = {
  storeId: string;
  currency: string;
  onChanged?: () => void;
};

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

const emptyForm = {
  label: "",
  amount: "",
  investment_date: todayISO(),
  note: "",
};

export function ManualInvestmentPanel({ storeId, currency, onChanged }: Props) {
  const [items, setItems] = useState<ManualInvestment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.analytics.listInvestments(storeId);
      setItems(res.investments);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load investments");
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    load();
  }, [load]);

  const resetForm = () => {
    setForm({ ...emptyForm, investment_date: todayISO() });
    setEditingId(null);
  };

  const startEdit = (item: ManualInvestment) => {
    setEditingId(item.id);
    setForm({
      label: item.label,
      amount: String(item.amount),
      investment_date: item.investment_date,
      note: item.note || "",
    });
    setMessage("");
    setError("");
  };

  const save = async () => {
    const label = form.label.trim();
    const amount = parseFloat(form.amount);
    if (!label) {
      setError("Enter a label for this investment");
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter an amount greater than 0");
      return;
    }
    if (!form.investment_date) {
      setError("Pick an investment date");
      return;
    }

    setSaving(true);
    setError("");
    setMessage("");
    try {
      const payload = {
        label,
        amount,
        investment_date: form.investment_date,
        note: form.note.trim() || null,
      };
      if (editingId) {
        await api.analytics.updateInvestment(storeId, editingId, payload);
        setMessage("Investment updated.");
      } else {
        await api.analytics.createInvestment(storeId, payload);
        setMessage("Investment added.");
      }
      resetForm();
      await load();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save investment");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this investment?")) return;
    setError("");
    setMessage("");
    try {
      await api.analytics.deleteInvestment(storeId, id);
      if (editingId === id) resetForm();
      setMessage("Investment deleted.");
      await load();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete investment");
    }
  };

  if (loading) {
    return (
      <Card padding="lg">
        <p className="text-content-muted text-sm">Loading investments…</p>
      </Card>
    );
  }

  return (
    <div className="space-y-4 w-full min-w-0">
      <Card padding="lg" className="border-brand-500/20 bg-brand-500/5">
        <div className="flex items-start gap-3">
          <Landmark className="h-5 w-5 text-brand-600 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <CardTitle>Manual investments</CardTitle>
            <CardDescription className="mt-1">
              Log cash you put into the business that APIs cannot track — agencies, tools,
              inventory deposits, freelancers, etc. Amounts dated in the selected dashboard
              period are deducted from net profit.
            </CardDescription>
          </div>
        </div>
      </Card>

      <Card padding="lg">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <h3 className="text-sm font-semibold text-content">
            {editingId ? "Edit investment" : "Add investment"}
          </h3>
          {editingId && (
            <Button type="button" variant="outline" size="sm" onClick={resetForm}>
              Cancel edit
            </Button>
          )}
        </div>
        <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          <Input
            label="Label"
            placeholder="e.g. Agency retainer"
            value={form.label}
            onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
          />
          <Input
            label={`Amount (${currency})`}
            type="number"
            min="0"
            step="0.01"
            placeholder="0.00"
            value={form.amount}
            onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
          />
          <Input
            label="Date"
            type="date"
            value={form.investment_date}
            onChange={(e) => setForm((f) => ({ ...f, investment_date: e.target.value }))}
          />
          <Input
            label="Note (optional)"
            placeholder="Context"
            value={form.note}
            onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
          />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button type="button" onClick={save} disabled={saving}>
            {editingId ? (
              <>
                <Pencil className="h-4 w-4 mr-1.5" />
                Update
              </>
            ) : (
              <>
                <Plus className="h-4 w-4 mr-1.5" />
                Add investment
              </>
            )}
          </Button>
          {message && <p className="text-sm text-emerald-600">{message}</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
      </Card>

      <Card padding="lg">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
          <div>
            <h3 className="text-sm font-semibold text-content">All investments</h3>
            <p className="text-xs text-content-muted mt-0.5">
              Sorted by date · deducted on the dashboard when the date falls in the selected period
            </p>
          </div>
          <Badge variant="muted">
            {items.length} · {formatMoney(total, currency)} total
          </Badge>
        </div>

        {items.length === 0 ? (
          <p className="text-sm text-content-muted">No manual investments yet.</p>
        ) : (
          <div className="divide-y divide-border">
            {items.map((item) => (
              <div
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
              >
                <div className="min-w-0">
                  <p className="font-medium text-content truncate">{item.label}</p>
                  <p className="text-xs text-content-muted mt-0.5">
                    {item.investment_date}
                    {item.note ? ` · ${item.note}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="font-semibold text-content tabular-nums">
                    {formatMoney(item.amount, currency)}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => startEdit(item)}
                    aria-label="Edit investment"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => remove(item.id)}
                    aria-label="Delete investment"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
