"""Meta (Facebook) Marketing API client for ad insights."""

from __future__ import annotations

import httpx

META_GRAPH_VERSION = "v21.0"
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

# Core fields used by Analytics profit dashboard (keep stable).
_ACCOUNT_FIELDS = (
    "spend,impressions,clicks,cpc,cpm,ctr,actions,action_values,purchase_roas"
)
_CAMPAIGN_FIELDS = (
    "campaign_id,campaign_name,spend,impressions,clicks,cpc,cpm,ctr,"
    "actions,action_values,purchase_roas"
)

# Richer fields for the dedicated Ads dashboard (creative + delivery health).
_ADS_DASHBOARD_ACCOUNT_FIELDS = (
    "spend,impressions,reach,frequency,clicks,cpc,cpm,ctr,"
    "inline_link_clicks,inline_link_click_ctr,"
    "outbound_clicks,outbound_clicks_ctr,"
    "actions,action_values,purchase_roas,cost_per_action_type,"
    "video_play_actions,video_thruplay_watched_actions,"
    "video_continuous_2_sec_watched_actions"
)
_ADS_DASHBOARD_CAMPAIGN_FIELDS = (
    "campaign_id,campaign_name,spend,impressions,reach,frequency,clicks,cpc,cpm,ctr,"
    "inline_link_clicks,inline_link_click_ctr,outbound_clicks,outbound_clicks_ctr,"
    "actions,action_values,purchase_roas,cost_per_action_type,"
    "video_play_actions,video_continuous_2_sec_watched_actions"
)
_ADS_DASHBOARD_ADSET_FIELDS = (
    "campaign_id,campaign_name,adset_id,adset_name,spend,impressions,reach,frequency,"
    "clicks,cpc,cpm,ctr,inline_link_clicks,outbound_clicks,"
    "actions,action_values,purchase_roas,cost_per_action_type,"
    "video_play_actions,video_continuous_2_sec_watched_actions"
)
_ADS_DASHBOARD_AD_FIELDS = (
    "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
    "spend,impressions,reach,frequency,clicks,cpc,cpm,ctr,"
    "inline_link_clicks,inline_link_click_ctr,outbound_clicks,outbound_clicks_ctr,"
    "actions,action_values,purchase_roas,cost_per_action_type,"
    "video_play_actions,video_continuous_2_sec_watched_actions,"
    "quality_ranking,engagement_rate_ranking,conversion_rate_ranking"
)


class MetaAdsClient:
    def __init__(self, access_token: str, ad_account_id: str) -> None:
        self.access_token = access_token.strip()
        account = ad_account_id.strip()
        if account.startswith("act_"):
            self.ad_account_id = account
        else:
            self.ad_account_id = f"act_{account}"

    async def test_connection(self) -> tuple[bool, str, str | None]:
        """Verify token and ad account access. Returns (ok, message, account_name)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{META_GRAPH_BASE}/{self.ad_account_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "name,account_status,currency",
                },
            )
            if resp.status_code != 200:
                err = resp.json().get("error", {})
                msg = err.get("message") or resp.text
                return False, f"Meta API error: {msg}", None
            data = resp.json()
            name = data.get("name") or self.ad_account_id
            status = data.get("account_status")
            if status not in (1, None):
                return False, f"Ad account '{name}' is not active (status {status})", name
            return True, f"Connected to {name}", name

    async def get_account_insights(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        date_preset: str | None = None,
        time_increment: int | str = 1,
    ) -> dict:
        """Account-level insights (single page). Prefer get_account_insights_all for long ranges."""
        return await self._fetch_insights(
            level="account",
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment=time_increment,
            breakdown_fields=_ACCOUNT_FIELDS,
        )

    async def get_account_insights_all(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        date_preset: str | None = None,
        time_increment: int | str = 1,
        max_pages: int = 50,
        rich: bool = False,
    ) -> list[dict]:
        """Paginate account insights so All-time daily rows are not truncated at 500."""
        fields = _ADS_DASHBOARD_ACCOUNT_FIELDS if rich else _ACCOUNT_FIELDS
        return await self._paginate_insights(
            level="account",
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment=time_increment,
            breakdown_fields=fields,
            max_pages=max_pages,
        )

    async def get_campaign_insights(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        date_preset: str | None = None,
        rich: bool = False,
    ) -> list[dict]:
        """Campaign-level insights for the period (paginated)."""
        fields = _ADS_DASHBOARD_CAMPAIGN_FIELDS if rich else _CAMPAIGN_FIELDS
        return await self._paginate_insights(
            level="campaign",
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment="all_days",
            breakdown_fields=fields,
            max_pages=20,
        )

    async def get_adset_insights(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        date_preset: str | None = None,
    ) -> list[dict]:
        return await self._paginate_insights(
            level="adset",
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment="all_days",
            breakdown_fields=_ADS_DASHBOARD_ADSET_FIELDS,
            max_pages=20,
        )

    async def get_ad_insights(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        date_preset: str | None = None,
    ) -> list[dict]:
        return await self._paginate_insights(
            level="ad",
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment="all_days",
            breakdown_fields=_ADS_DASHBOARD_AD_FIELDS,
            max_pages=30,
        )

    async def get_account_insights_attribution(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        date_preset: str | None = None,
        windows: list[str] | None = None,
    ) -> list[dict]:
        """Account insights with explicit attribution windows for 1d vs 7d click comparison."""
        attribution = windows or ["1d_click", "7d_click", "1d_view"]
        return await self._paginate_insights(
            level="account",
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment="all_days",
            breakdown_fields="spend,actions,action_values,purchase_roas",
            max_pages=5,
            action_attribution_windows=attribution,
        )

    async def _paginate_insights(
        self,
        *,
        level: str,
        since: str | None,
        until: str | None,
        date_preset: str | None,
        time_increment: int | str,
        breakdown_fields: str,
        max_pages: int,
        action_attribution_windows: list[str] | None = None,
    ) -> list[dict]:
        first = await self._fetch_insights(
            level=level,
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment=time_increment,
            breakdown_fields=breakdown_fields,
            action_attribution_windows=action_attribution_windows,
        )
        rows = list(first.get("data") or [])
        next_url = (first.get("paging") or {}).get("next")
        pages = 1
        async with httpx.AsyncClient(timeout=60) as client:
            while next_url and pages < max_pages:
                resp = await client.get(next_url)
                resp.raise_for_status()
                payload = resp.json()
                batch = list(payload.get("data") or [])
                rows.extend(batch)
                next_url = (payload.get("paging") or {}).get("next")
                pages += 1
                if not batch:
                    break
        return rows

    async def _fetch_insights(
        self,
        *,
        level: str,
        since: str | None,
        until: str | None,
        date_preset: str | None = None,
        time_increment: int | str,
        breakdown_fields: str,
        action_attribution_windows: list[str] | None = None,
    ) -> dict:
        params: dict[str, str | int] = {
            "access_token": self.access_token,
            "fields": breakdown_fields,
            "time_increment": time_increment,
            "level": level,
            "limit": 500,
        }
        if date_preset:
            params["date_preset"] = date_preset
        elif since and until:
            params["time_range"] = f'{{"since":"{since}","until":"{until}"}}'
        else:
            raise ValueError("Either date_preset or since/until must be provided")
        if action_attribution_windows:
            # Graph API expects a JSON-like array string
            params["action_attribution_windows"] = (
                "[" + ",".join(f'"{w}"' for w in action_attribution_windows) + "]"
            )
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.get(
                f"{META_GRAPH_BASE}/{self.ad_account_id}/insights",
                params=params,
            )
            resp.raise_for_status()
            return resp.json()


# Preferred action types (first match wins) for purchase counting / value.
_PURCHASE_ACTION_TYPES = (
    "omni_purchase",
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "onsite_web_purchase",
    "web_in_store_purchase",
)

# Funnel / engagement action types to surface in analytics.
_FUNNEL_ACTION_ALIASES: dict[str, tuple[str, ...]] = {
    "add_to_cart": (
        "omni_add_to_cart",
        "add_to_cart",
        "offsite_conversion.fb_pixel_add_to_cart",
    ),
    "initiate_checkout": (
        "omni_initiated_checkout",
        "initiate_checkout",
        "offsite_conversion.fb_pixel_initiate_checkout",
    ),
    "view_content": (
        "omni_view_content",
        "view_content",
        "offsite_conversion.fb_pixel_view_content",
    ),
    "landing_page_view": ("landing_page_view",),
    "link_click": ("link_click",),
}


def parse_meta_actions(actions: list[dict] | None, action_type: str) -> float:
    if not actions:
        return 0.0
    for action in actions:
        if action.get("action_type") == action_type:
            try:
                return float(action.get("value") or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def parse_meta_action_first(actions: list[dict] | None, action_types: tuple[str, ...]) -> float:
    """Return the first matching action value from a preferred type list."""
    for action_type in action_types:
        count = parse_meta_actions(actions, action_type)
        if count > 0:
            return count
    return 0.0


def parse_meta_purchases(actions: list[dict] | None) -> float:
    return parse_meta_action_first(actions, _PURCHASE_ACTION_TYPES)


def parse_meta_purchase_value(action_values: list[dict] | None) -> float:
    return parse_meta_action_first(action_values, _PURCHASE_ACTION_TYPES)


def parse_meta_funnel(actions: list[dict] | None) -> dict[str, float]:
    """Extract common funnel metrics from Meta actions."""
    return {
        key: parse_meta_action_first(actions, aliases)
        for key, aliases in _FUNNEL_ACTION_ALIASES.items()
    }


def parse_meta_purchase_roas(purchase_roas: list[dict] | None) -> float:
    """Parse purchase_roas field from Meta insights (ratio, not percentage)."""
    if not purchase_roas:
        return 0.0
    for item in purchase_roas:
        action_type = item.get("action_type") or ""
        if action_type in _PURCHASE_ACTION_TYPES or action_type.endswith("purchase"):
            try:
                return float(item.get("value") or 0)
            except (TypeError, ValueError):
                return 0.0
    # Fallback: first reported ROAS entry
    try:
        return float((purchase_roas[0] or {}).get("value") or 0)
    except (TypeError, ValueError, IndexError):
        return 0.0


def _sum_video_action_values(entries: list[dict] | None) -> float:
    if not entries:
        return 0.0
    total = 0.0
    for item in entries:
        try:
            total += float(item.get("value") or 0)
        except (TypeError, ValueError):
            continue
    return total


def parse_meta_video_3s_plays(row: dict) -> float:
    """3-second video plays (hook). Prefer video_play_actions; fall back to actions.video_view."""
    plays = _sum_video_action_values(row.get("video_play_actions"))
    if plays > 0:
        return plays
    return parse_meta_actions(row.get("actions"), "video_view")


def parse_meta_video_2s_plays(row: dict) -> float:
    return _sum_video_action_values(row.get("video_continuous_2_sec_watched_actions"))


def parse_meta_outbound_clicks(row: dict) -> float:
    clicks = _sum_video_action_values(row.get("outbound_clicks"))
    if clicks > 0:
        return clicks
    try:
        return float(row.get("inline_link_clicks") or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_meta_outbound_ctr(row: dict, impressions: float) -> float:
    """Outbound CTR as a percentage."""
    raw = row.get("outbound_clicks_ctr")
    if isinstance(raw, list) and raw:
        try:
            return float(raw[0].get("value") or 0)
        except (TypeError, ValueError, IndexError):
            pass
    try:
        inline = float(row.get("inline_link_click_ctr") or 0)
        if inline > 0:
            return inline
    except (TypeError, ValueError):
        pass
    outbound = parse_meta_outbound_clicks(row)
    if impressions > 0 and outbound > 0:
        return (outbound / impressions) * 100
    return 0.0


def parse_meta_cpa(row: dict, purchases: float) -> float:
    """Cost per purchase from cost_per_action_type, else spend / purchases."""
    for item in row.get("cost_per_action_type") or []:
        action_type = item.get("action_type") or ""
        if action_type in _PURCHASE_ACTION_TYPES or action_type.endswith("purchase"):
            try:
                return float(item.get("value") or 0)
            except (TypeError, ValueError):
                return 0.0
    try:
        spend = float(row.get("spend") or 0)
    except (TypeError, ValueError):
        spend = 0.0
    if purchases > 0:
        return spend / purchases
    return 0.0


def parse_meta_float(row: dict, key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def hook_rate(video_3s: float, impressions: float) -> float:
    """Percent of impressions that watched 3s — creative thumb-stop strength."""
    if impressions <= 0:
        return 0.0
    return (video_3s / impressions) * 100
