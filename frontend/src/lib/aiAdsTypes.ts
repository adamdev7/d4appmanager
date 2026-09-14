export type AIAdsJobStatus =
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "PARTIAL"
  | "FAILED"
  | "CANCELLED";

export type CreativeStatus =
  | "DRAFT"
  | "QUEUED"
  | "GENERATING"
  | "READY"
  | "APPROVED"
  | "REJECTED"
  | "PUBLISHED"
  | "PAUSED"
  | "ARCHIVED"
  | "FAILED";

export type AIAdsOverview = {
  generated_this_week: { images: number; videos: number };
  imported_meta_creatives: number;
  analyzed_creatives: number;
  top_creative: AIAdsGeneratedCreative | null;
  current_strategy: AIAdsStrategy | null;
  recommendations: AIAdsRecommendation[];
  active_job: AIAdsJob | null;
  workplace_job?: AIAdsJob | null;
  last_sync_at: string | null;
  last_analyze_at: string | null;
  openai_configured: boolean;
};

export type AIAdsProduct = {
  id: string;
  title: string;
  price: number | null;
  currency: string | null;
  image: string | null;
  product_url: string | null;
};

export type AIAdsPerformance = {
  impressions?: number | null;
  reach?: number | null;
  clicks?: number | null;
  spend?: number | null;
  ctr?: number | null;
  cpc?: number | null;
  cpm?: number | null;
  purchases?: number | null;
  cpa?: number | null;
  conversion_value?: number | null;
  roas?: number | null;
  video_views?: number | null;
  frequency?: number | null;
  date_range_start?: string | null;
  date_range_end?: string | null;
  insufficient_data?: boolean;
  ad_id?: string | null;
};

export type AIAdsMetaCreative = {
  id: string;
  source: "META";
  campaign_name?: string | null;
  ad_name?: string | null;
  ad_id?: string | null;
  format?: string;
  headline?: string | null;
  primary_text?: string | null;
  cta?: string | null;
  preview_url?: string | null;
  performance?: AIAdsPerformance;
  dna?: {
    visual?: Record<string, unknown>;
    copy?: Record<string, unknown>;
    format?: Record<string, unknown>;
    performance?: Record<string, unknown>;
    analysis_basis?: string | null;
  };
  analysis?: { observed?: string[]; interpretation?: string[] };
  updated_at?: string | null;
};

export type AIAdsGeneratedCreative = {
  id: string;
  source: "AI_GENERATED";
  user_id?: string | null;
  type?: string;
  status?: CreativeStatus | string;
  product_id?: string | null;
  hook?: string | null;
  headline?: string | null;
  primary_text?: string | null;
  cta?: string | null;
  preview_url?: string | null;
  video_url?: string | null;
  has_rendered_media?: boolean;
  meta_ad_id?: string | null;
  ai_score?: number | null;
  score_label?: string;
  score_breakdown?: Record<string, number>;
  source_strategy_id?: string | null;
  source_creative_ids?: string[];
  rationale?: string | null;
  visual_direction?: string | null;
  aspect_ratio?: string | null;
  placement?: string | null;
  video_spec?: unknown;
  storyboard?: {
    hook?: string | null;
    duration?: number | null;
    format?: string | null;
    cta?: string | null;
    scenes?: Array<{
      duration?: number | null;
      visual?: string | null;
      text_overlay?: string | null;
      voiceover?: string | null;
    }>;
  } | null;
  failure_reason?: string | null;
  created_at?: string | null;
};

export type AIAdsJobLogEntry = {
  at?: string;
  step?: string;
  title?: string;
  detail?: string;
  pct?: number;
};

export type AIAdsJob = {
  job_id: string;
  id: string;
  status: AIAdsJobStatus | string;
  product_id?: string | null;
  progress_message?: string;
  progress_step?: string;
  progress_pct?: number;
  progress_log?: AIAdsJobLogEntry[];
  thinking?: string;
  total_items?: number;
  completed_items?: number;
  failed_items?: number;
  error_message?: string | null;
  strategy_id?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  worker_alive?: boolean;
  swept_count?: number;
  nudge?: string;
  creatives?: AIAdsGeneratedCreative[];
};

export type AIAdsStrategy = {
  id: string;
  product_id?: string | null;
  summary: string;
  target_audience?: string;
  confidence?: number;
  strategy?: Record<string, unknown>;
  intelligence_report?: Record<string, unknown>;
  created_at?: string | null;
};

export type AIAdsRecommendation = {
  id: string;
  title: string;
  explanation: string;
  supporting_creative_ids?: string[];
  supporting_metrics?: Record<string, unknown>;
  confidence?: number;
  recommended_action?: string;
  created_at?: string | null;
};

export type AIAdsSettings = {
  store_id: string;
  weekly_generation_enabled: boolean;
  generation_day: string;
  image_count: number;
  video_count: number;
  auto_publish: boolean;
  env_auto_publish: boolean;
  winner_pct: number;
  combination_pct: number;
  exploration_pct: number;
  experimental_pct: number;
  brand_style: string;
  default_audience: string;
  default_objective: string;
  default_placement: string;
  default_aspect_ratio: string;
  creative_styles: string[];
  meta_page_id: string | null;
  last_sync_at: string | null;
  last_analyze_at: string | null;
  meta_configured: boolean;
  openai_configured: boolean;
  openai_key_masked: string | null;
  strategy_model: string;
  analysis_model: string;
  creative_model: string;
  image_model: string;
  video_model?: string;
};

export type AIAdsAdset = {
  id: string;
  name: string;
  status?: string | null;
  campaign_id?: string | null;
};

export type AIAdsAvatar = {
  id: string;
  name: string;
  image_url: string | null;
  description: string;
  usage_rules: string;
  active: boolean;
};

export type AIAdsLibrary = {
  meta: AIAdsMetaCreative[];
  generated: AIAdsGeneratedCreative[];
};
