import { useEffect, useState } from "react";
import { api, type TextModelChoice } from "@/lib/api";
import { Select } from "@/components/ui/Select";

const FALLBACK: TextModelChoice[] = [
  {
    id: "gpt-6.1-sol",
    name: "Sol",
    tag: "Best value",
    blurb:
      "Near flagship quality at about one fifth of the price. Default for replies, reports, and ad copy.",
    input_per_mtok: 2,
    output_per_mtok: 10,
    recommended: true,
  },
  {
    id: "gpt-6-luna",
    name: "Luna",
    tag: "Lowest spend",
    blurb: "The cheap model for short, high-volume replies.",
    input_per_mtok: 0.1,
    output_per_mtok: 0.5,
    recommended: false,
  },
  {
    id: "gpt-6-astra",
    name: "Astra",
    tag: "Highest quality",
    blurb: "Flagship. Worth it for long reports and creative briefs.",
    input_per_mtok: 10,
    output_per_mtok: 50,
    recommended: false,
  },
];

type Props = {
  value: string;
  onChange: (modelId: string) => void;
  label?: string;
};

export function ModelSelect({ value, onChange, label = "Model" }: Props) {
  const [models, setModels] = useState<TextModelChoice[]>(FALLBACK);

  useEffect(() => {
    api.connections
      .models()
      .then((data) => {
        if (data.models?.length) setModels(data.models);
      })
      .catch(() => setModels(FALLBACK));
  }, []);

  const selected =
    models.find((model) => model.id === value) ??
    models.find((model) => model.recommended) ??
    models[0];
  const known = models.some((model) => model.id === value);

  return (
    <div className="space-y-2">
      <Select label={label} value={value} onChange={(e) => onChange(e.target.value)}>
        {models.map((model) => (
          <option key={model.id} value={model.id}>
            {model.name} — {model.tag}
            {model.recommended ? " (default)" : ""}
          </option>
        ))}
        {!known && value && <option value={value}>{value} — saved earlier</option>}
      </Select>
      {selected && (
        <p className="text-xs text-content-subtle leading-relaxed">
          {selected.blurb} About ${selected.input_per_mtok} in / ${selected.output_per_mtok} out
          per million tokens.
        </p>
      )}
    </div>
  );
}
