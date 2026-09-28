export type DirectorAggressiveness = "safe" | "balanced" | "bold";

export type DirectorOffer = { id: string; label: string; details: string };

export type DirectorSettings = {
  enabled: boolean;
  drive_weekly: boolean;
  challenge_requests: boolean;
  aggressiveness: DirectorAggressiveness;
  weekly_credit_cap_usd: number;
  priority_product_ids: string[];
  excluded_product_ids: string[];
  offers: DirectorOffer[];
  never_do: string[];
  margin_floor_pct: number | null;
  low_stock_threshold: number;
  copy_language: "auto" | "en" | "fr";
  last_run_at: string | null;
  server_enabled: boolean;
};

export type DirectorSettingsUpdate = Partial<
  Omit<DirectorSettings, "last_run_at" | "server_enabled" | "offers">
> & { offers?: Array<Partial<DirectorOffer>> };

export type DirectorBudget = {
  spent_usd: number;
  cap_usd: number;
  remaining_usd: number | null;
  rates: { image_usd: number; video_usd: number; plan_usd: number; director_run_usd: number };
};

export type DirectorFlag = { code: string; message: string };

export type DirectorScript = {
  first_two_seconds?: string;
  lines?: string[];
  cta?: string;
  language?: string;
};

export type DirectorSuggestionStatus = "NEW" | "SAVED" | "DISMISSED" | "GENERATED" | "EXPIRED";

export type DirectorSuggestion = {
  id: string;
  report_id: string | null;
  kind: "new" | "refresh" | "clone" | "wildcard" | string;
  status: DirectorSuggestionStatus;
  in_brief: boolean;
  is_experiment: boolean;
  concept_name: string;
  ad_type: string;
  ad_type_label: string;
  product_id: string | null;
  product_title: string;
  image_count: number;
  video_count: number;
  hook: string;
  hook_type: string;
  angle: string;
  emotion: string;
  funnel: string;
  audience: string;
  occasion: string;
  why: string;
  rationale: string;
  hypothesis: string;
  test_variable: string;
  test_design: string;
  test_budget: string;
  ad_name: string;
  script: DirectorScript;
  scores: {
    brand_fit?: number;
    novelty?: number;
    predicted_performance?: number;
    production_cost?: number;
    risk?: number;
    score?: number;
    measured_novelty?: number;
    verdict?: string;
  };
  flags: DirectorFlag[];
  estimated_cost_usd: number;
  source_creative_id: string | null;
  dismiss_reason: string | null;
  job_id: string | null;
  outcome: {
    job_status?: string | null;
    made?: number;
    approved?: number;
    rejected?: number;
    published?: number;
    performance?: { ctr?: number | null; roas?: number | null; spend?: number; frequency?: number | null } | null;
    summary?: string;
  };
  decided_at: string | null;
  created_at: string | null;
};

export type DirectorBriefItem = {
  index: number;
  image_count: number;
  video_count: number;
  reason: string;
  estimated_cost_usd: number;
  suggestion_id: string;
};

export type DirectorBrief = {
  headline?: string;
  summary?: string;
  testing_plan?: string;
  naming_convention?: string;
  budget_note?: string;
  items?: DirectorBriefItem[];
  total_images?: number;
  total_videos?: number;
  estimated_cost_usd?: number;
  filtered_out?: Array<{ concept_name?: string; reason: string }>;
};

export type DirectorAlert = {
  type: "fatigue" | "winner" | "stock" | "occasion" | string;
  level: "info" | "warning";
  title: string;
  message: string;
  creative_id?: string;
  product_id?: string;
  occasion?: string;
};

export type DirectorAudienceIdea = { name: string; segment_type: string; description: string; why: string };

export type DirectorOfferIdea = {
  label: string;
  offer_id: string;
  description: string;
  why: string;
  requires_confirmation: boolean;
};

export type DirectorReport = {
  id: string;
  trigger: "manual" | "weekly" | string;
  week_key: string | null;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  progress: string | null;
  brief: DirectorBrief;
  alerts: DirectorAlert[];
  audience_ideas: DirectorAudienceIdea[];
  offer_ideas: DirectorOfferIdea[];
  data_gaps: string[];
  estimated_cost_usd: number | null;
  model_used: string | null;
  weekly_run_id: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
};

export type DirectorPlaybookEntry = {
  id: string;
  kind: "hypothesis" | "learning" | "preference";
  statement: string;
  status: string;
  source: string;
  evidence: Array<{ at: string; source: string; note: string }>;
  updated_at: string | null;
};

export type DirectorAdType = {
  id: string;
  label: string;
  style: string;
  media: string[];
  description: string;
};

export type DirectorOverview = {
  settings: DirectorSettings;
  budget: DirectorBudget;
  latest_run: DirectorReport | null;
  report: DirectorReport | null;
  board: DirectorSuggestion[];
  log: DirectorSuggestion[];
  playbook: DirectorPlaybookEntry[];
  ad_types: DirectorAdType[];
};

export type DirectorSuggestionEdit = Partial<
  Pick<
    DirectorSuggestion,
    | "concept_name"
    | "ad_type"
    | "product_id"
    | "hook"
    | "angle"
    | "audience"
    | "hypothesis"
    | "test_design"
    | "image_count"
    | "video_count"
  >
>;

export type DirectorAlternative = {
  ad_type: string;
  ad_type_label?: string;
  hook: string;
  angle: string;
  audience: string;
  product_id: string;
  why: string;
};

export type DirectorChallenge = {
  verdict: "go" | "reconsider";
  notes: string[];
  alternative: DirectorAlternative | null;
  skipped: boolean;
};
