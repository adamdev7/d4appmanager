export type MdOutputFormat = "auto" | "jpeg" | "png";

export type MdSeverity = "critical" | "high" | "medium" | "low";

export type MdVerdict = "ai_labeled" | "ai_traces" | "metadata" | "clean";

export type MdFinding = {
  code: string;
  severity: MdSeverity;
  label: string;
  detail: string;
  location: string;
  meta_signal: boolean;
};

export type MdCheck = {
  id: string;
  label: string;
  passed: boolean;
  count: number;
};

export type MdScanReport = {
  verdict: MdVerdict;
  container: string;
  filename: string;
  size_bytes: number;
  image: { format: string | null; width: number; height: number; mode: string; frames: number } | null;
  meta_signals: number;
  findings: MdFinding[];
  checks: MdCheck[];
  structure: string[];
};

export type MdCleanResult = {
  filename: string;
  mime: string;
  format: "jpeg" | "png";
  width: number;
  height: number;
  size_bytes: number;
  data_base64: string;
  removed: MdFinding[];
  removed_count: number;
  meta_signals_removed: number;
  before: MdScanReport;
  after: MdScanReport;
  fidelity: { lossless: boolean; psnr_db: number | null; label: string };
  notes: string[];
  passes: number;
};
