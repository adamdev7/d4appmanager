import { useState } from "react";
import { Link } from "react-router-dom";
import { Bookmark, Lightbulb, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { DirectorChallenge } from "@/lib/directorTypes";
import { Button } from "@/components/ui/Button";

export function DirectorChallengePanel({
  storeId,
  challenge,
  requestBody,
  onGenerateAsked,
  onJobStarted,
  onClose,
}: {
  storeId: string;
  challenge: DirectorChallenge;
  requestBody: Record<string, unknown>;
  onGenerateAsked: () => void;
  onJobStarted: (jobId: string) => void;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState<"" | "use" | "save">("");
  const [savedId, setSavedId] = useState("");
  const [error, setError] = useState("");
  const alt = challenge.alternative;

  async function saveAlternative() {
    if (!alt) return "";
    if (savedId) return savedId;
    const saved = await api.aiAds.saveDirectorAlternative(storeId, alt, requestBody);
    setSavedId(saved.id);
    return saved.id;
  }

  async function useDirectorVersion() {
    setBusy("use");
    setError("");
    try {
      const id = await saveAlternative();
      let result;
      try {
        result = await api.aiAds.generateSuggestion(storeId, id);
      } catch (e) {
        const status = (e as { status?: number }).status;
        const message = e instanceof Error ? e.message : "";
        if (status !== 409 || !window.confirm(`${message}\n\nGenerate anyway?`)) throw e;
        result = await api.aiAds.generateSuggestion(storeId, id, true);
      }
      onJobStarted(result.job.job_id || result.job.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not generate the Director's version");
    } finally {
      setBusy("");
    }
  }

  async function saveForLater() {
    setBusy("save");
    setError("");
    try {
      await saveAlternative();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the alternative");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3.5 text-sm">
      <p className="flex items-center gap-2 font-medium">
        <Lightbulb className="h-4 w-4 text-amber-600" />
        Creative Director: second opinion
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-content-muted">
        {challenge.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>

      {alt && (
        <div className="mt-3 rounded-md border border-border bg-surface p-2.5 text-xs">
          <p className="font-medium text-content">
            Suggested instead{alt.ad_type_label ? ` · ${alt.ad_type_label}` : ""}
          </p>
          {alt.hook && <p className="mt-1">Hook: “{alt.hook}”</p>}
          {alt.angle && <p>Angle: {alt.angle}</p>}
          {alt.audience && <p>Audience: {alt.audience}</p>}
          {alt.why && <p className="mt-1 text-content-muted">Why: {alt.why}</p>}
        </div>
      )}

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      {savedId && busy === "" && (
        <p className="mt-2 text-xs text-emerald-600">
          Saved. Find it under “Saved for later” on the{" "}
          <Link to="/ai-ads/director" className="underline">
            Director
          </Link>{" "}
          tab.
        </p>
      )}

      <div className="mt-3 flex flex-col gap-2">
        <Button size="sm" onClick={onGenerateAsked} disabled={busy !== ""}>
          <Sparkles className="h-3.5 w-3.5" />
          Generate exactly what I asked
        </Button>
        {alt && (
          <Button size="sm" variant="outline" onClick={() => void useDirectorVersion()} isLoading={busy === "use"}>
            Use the Director's version
          </Button>
        )}
        {alt && !savedId && (
          <Button size="sm" variant="ghost" onClick={() => void saveForLater()} isLoading={busy === "save"}>
            <Bookmark className="h-3.5 w-3.5" />
            Save alternative for later
          </Button>
        )}
        <button type="button" className="text-xs text-content-subtle underline" onClick={onClose}>
          Back to editing
        </button>
      </div>
    </div>
  );
}
