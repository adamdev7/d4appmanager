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
# Link-click CPC/CTR fields match Ads Manager's default "CPC (cost per link click)"
# and "CTR (link click-through rate)" columns — not all-clicks cpc/ctr.
_ADS_LINK_FIELDS = (
    "inline_link_clicks,inline_link_click_ctr,cost_per_inline_link_click,"
    "outbound_clicks,outbound_clicks_ctr,cost_per_outbound_click,website_ctr"
)
# results/cost_per_result are Ads Manager result columns; valid on campaign/adset/ad.
_ADS_RESULT_FIELDS = "results,cost_per_result"
_ADS_DASHBOARD_ACCOUNT_FIELDS = (
    "spend,impressions,reach,frequency,clicks,cpc,cpm,ctr,"
    f"{_ADS_LINK_FIELDS},"
    "actions,action_values,purchase_roas,cost_per_action_type,"
    "video_play_actions,video_thruplay_watched_actions,"
    "video_continuous_2_sec_watched_actions"
)
_ADS_DASHBOARD_CAMPAIGN_FIELDS = (
    "campaign_id,campaign_name,spend,impressions,reach,frequency,clicks,cpc,cpm,ctr,"
    f"{_ADS_LINK_FIELDS},{_ADS_RESULT_FIELDS},"
    "actions,action_values,purchase_roas,cost_per_action_type,"
    "video_play_actions,video_continuous_2_sec_watched_actions"
)
_ADS_DASHBOARD_ADSET_FIELDS = (
    "campaign_id,campaign_name,adset_id,adset_name,spend,impressions,reach,frequency,"
    "clicks,cpc,cpm,ctr,"
    f"{_ADS_LINK_FIELDS},{_ADS_RESULT_FIELDS},"
    "actions,action_values,purchase_roas,cost_per_action_type,"
    "video_play_actions,video_continuous_2_sec_watched_actions"
)
_ADS_DASHBOARD_AD_FIELDS = (
    "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,"
    "spend,impressions,reach,frequency,clicks,cpc,cpm,ctr,"
    f"{_ADS_LINK_FIELDS},{_ADS_RESULT_FIELDS},"
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

    async def get_account_currency(self) -> str | None:
        """Return the Meta ad account billing currency (e.g. CAD). Never assume store currency."""
        info = await self.get_account_info()
        return info.get("currency")

    async def get_account_info(self) -> dict:
        """Ad account billing currency + timezone (Ads Manager dates use this TZ)."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{META_GRAPH_BASE}/{self.ad_account_id}",
                params={
                    "access_token": self.access_token,
                    "fields": "name,currency,timezone_name,account_status",
                },
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
            currency = (data.get("currency") or "").strip().upper()
            return {
                "name": data.get("name") or self.ad_account_id,
                "currency": currency or None,
                "timezone_name": (data.get("timezone_name") or "").strip() or None,
                "account_status": data.get("account_status"),
            }

    async def list_campaigns(self) -> list[dict]:
        return await self._paginate_edge(
            "campaigns",
            "id,name,effective_status,status,objective",
        )

    async def list_adsets(self) -> list[dict]:
        return await self._paginate_edge(
            "adsets",
            "id,name,campaign_id,effective_status,status",
        )

    async def list_ads(self) -> list[dict]:
        return await self._paginate_edge(
            "ads",
            "id,name,adset_id,campaign_id,effective_status,status",
        )

    async def list_ads_with_creatives(self) -> list[dict]:
        """Ads plus nested creative objects (copy, image/video refs). Fields may be null."""
        fields = (
            "id,name,adset_id,campaign_id,effective_status,status,created_time,"
            "creative{"
            "id,name,title,body,image_url,thumbnail_url,object_type,video_id,"
            "image_hash,link_url,call_to_action_type,effective_object_story_id,"
            "object_story_spec,asset_feed_spec,url_tags,status,thumbnail_id"
            "}"
        )
        return await self._paginate_edge("ads", fields, max_pages=15)

    async def get_object(self, object_id: str, fields: str) -> dict:
        oid = str(object_id or "").strip()
        if not oid:
            return {}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{META_GRAPH_BASE}/{oid}",
                params={"access_token": self.access_token, "fields": fields},
            )
            if resp.status_code != 200:
                return {}
            data = resp.json()
            return data if isinstance(data, dict) else {}

    async def get_video_meta(self, video_id: str) -> dict:
        return await self.get_object(
            video_id, "id,title,picture,source,length,thumbnails{uri,height,width}"
        )

    async def download_url(self, url: str, *, timeout: float = 45) -> bytes | None:
        """Download a remote asset. Meta CDN URLs often already include a signature."""
        if not url:
            return None
        params: dict[str, str] = {}
        if "access_token=" not in url and "fbcdn" in url.lower():
            params["access_token"] = self.access_token
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url, params=params or None)
                if resp.status_code != 200:
                    return None
                return resp.content
        except Exception:
            return None

    async def upload_ad_image(self, data: bytes, filename: str = "creative.png") -> dict:
        """Upload image bytes and return {hash, url, name}."""
        import base64

        if not data:
            raise ValueError("Empty image upload")
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{META_GRAPH_BASE}/{self.ad_account_id}/adimages",
                params={"access_token": self.access_token},
                data={"bytes": base64.b64encode(data).decode("ascii"), "name": filename},
            )
        payload = _meta_json(resp)
        images = payload.get("images") if isinstance(payload.get("images"), dict) else {}
        first = next(iter(images.values()), None) if images else None
        if not isinstance(first, dict) or not first.get("hash"):
            raise RuntimeError(payload.get("error", {}).get("message") or "Meta image upload returned no hash")
        return {
            "hash": first.get("hash"),
            "url": first.get("url"),
            "name": next(iter(images.keys()), filename),
        }

    async def upload_ad_video(self, data: bytes, filename: str = "creative.mp4") -> dict:
        """Upload an MP4 and return {id}."""
        if not data:
            raise ValueError("Empty video upload")
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{META_GRAPH_BASE}/{self.ad_account_id}/advideos",
                params={"access_token": self.access_token},
                files={"source": (filename, data, "video/mp4")},
            )
        payload = _meta_json(resp)
        video_id = payload.get("id")
        if not video_id:
            raise RuntimeError(payload.get("error", {}).get("message") or "Meta video upload returned no id")
        return {"id": str(video_id)}

    async def wait_for_video(self, video_id: str, *, timeout_seconds: int = 180) -> dict:
        import asyncio

        elapsed = 0
        last: dict = {}
        while elapsed <= timeout_seconds:
            last = await self.get_object(video_id, "id,status,picture,title,length")
            status = last.get("status")
            video_status = ""
            if isinstance(status, dict):
                video_status = str(status.get("video_status") or status.get("processing_phase") or "")
            elif status:
                video_status = str(status)
            if video_status.lower() in ("ready", "complete", "completed") or last.get("picture"):
                return last
            if video_status.lower() in ("error", "failed"):
                raise RuntimeError(f"Meta video processing failed ({video_status})")
            await asyncio.sleep(4)
            elapsed += 4
        return last

    async def create_ad_creative(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{META_GRAPH_BASE}/{self.ad_account_id}/adcreatives",
                params={"access_token": self.access_token},
                json=payload,
            )
            return _meta_json(resp)

    async def create_ad(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{META_GRAPH_BASE}/{self.ad_account_id}/ads",
                params={"access_token": self.access_token},
                json=payload,
            )
            return _meta_json(resp)

    async def update_ad_status(self, ad_id: str, status: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{META_GRAPH_BASE}/{ad_id}",
                params={"access_token": self.access_token},
                json={"status": status},
            )
            resp.raise_for_status()
            return resp.json()

    async def _paginate_edge(self, edge: str, fields: str, max_pages: int = 8) -> list[dict]:
        params: dict[str, str | int] = {
            "access_token": self.access_token,
            "fields": fields,
            "limit": 200,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"{META_GRAPH_BASE}/{self.ad_account_id}/{edge}",
                params=params,
            )
            resp.raise_for_status()
            payload = resp.json()
            rows = list(payload.get("data") or [])
            next_url = (payload.get("paging") or {}).get("next")
            pages = 1
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
            use_unified_attribution_setting=rich,
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
            use_unified_attribution_setting=rich,
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
            use_unified_attribution_setting=True,
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
            use_unified_attribution_setting=True,
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
        use_unified_attribution_setting: bool = False,
    ) -> list[dict]:
        first = await self._fetch_insights(
            level=level,
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment=time_increment,
            breakdown_fields=breakdown_fields,
            action_attribution_windows=action_attribution_windows,
            use_unified_attribution_setting=use_unified_attribution_setting,
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
        use_unified_attribution_setting: bool = False,
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
        if use_unified_attribution_setting:
            # Match Ads Manager's account-level attribution instead of API defaults.
            params["use_unified_attribution_setting"] = "true"
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.get(
                f"{META_GRAPH_BASE}/{self.ad_account_id}/insights",
                params=params,
            )
            if resp.status_code == 400:
                err = ""
                try:
                    err = str((resp.json().get("error") or {}).get("message") or resp.text).lower()
                except Exception:
                    err = (resp.text or "").lower()
                drop = [
                    field
                    for field in ("results", "cost_per_result", "website_ctr")
                    if field in breakdown_fields.split(",") and field in err
                ]
                if not drop and ("results" in err or "cost_per_result" in err):
                    drop = ["results", "cost_per_result"]
                if drop:
                    stripped = ",".join(
                        f for f in breakdown_fields.split(",") if f.strip() not in drop
                    )
                    params["fields"] = stripped
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


def _first_insight_value(raw) -> float:
    """Read a Meta insights metric that may be a scalar or [{value}] / [{values:[{value}]}]."""
    if raw is None or raw == "":
        return 0.0
    if isinstance(raw, list):
        if not raw:
            return 0.0
        return _first_insight_value(raw[0])
    if isinstance(raw, dict):
        nested = raw.get("values")
        if isinstance(nested, list) and nested:
            return _first_insight_value(nested[0])
        try:
            return float(raw.get("value") or 0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def parse_meta_outbound_clicks(row: dict) -> float:
    clicks = _sum_video_action_values(row.get("outbound_clicks"))
    if clicks > 0:
        return clicks
    try:
        return float(row.get("inline_link_clicks") or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_meta_link_clicks(row: dict) -> float:
    """Ads Manager 'link clicks' — inline link clicks, then outbound."""
    try:
        inline = float(row.get("inline_link_clicks") or 0)
        if inline > 0:
            return inline
    except (TypeError, ValueError):
        pass
    return parse_meta_outbound_clicks(row)


def parse_meta_outbound_ctr(row: dict, impressions: float) -> float:
    """Outbound CTR as a percentage."""
    raw = row.get("outbound_clicks_ctr")
    listed = _first_insight_value(raw)
    if listed > 0:
        return listed
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


def parse_meta_link_ctr(row: dict, impressions: float) -> float:
    """Ads Manager CTR (link click-through rate), as a percentage."""
    website = _first_insight_value(row.get("website_ctr"))
    if website > 0:
        return website
    try:
        inline = float(row.get("inline_link_click_ctr") or 0)
        if inline > 0:
            return inline
    except (TypeError, ValueError):
        pass
    return parse_meta_outbound_ctr(row, impressions)


def parse_meta_link_cpc(row: dict, spend: float, link_clicks: float) -> float:
    """Ads Manager CPC (cost per link click)."""
    inline = _first_insight_value(row.get("cost_per_inline_link_click"))
    if inline > 0:
        return inline
    outbound = _first_insight_value(row.get("cost_per_outbound_click"))
    if outbound > 0:
        return outbound
    if link_clicks > 0 and spend > 0:
        return spend / link_clicks
    return parse_meta_float(row, "cpc")


# Ads Manager "Website purchases" cost/result uses pixel purchase before omni aggregates.
_ADS_MANAGER_PURCHASE_COST_TYPES = (
    "offsite_conversion.fb_pixel_purchase",
    "purchase",
    "omni_purchase",
    "onsite_web_purchase",
    "web_in_store_purchase",
)


def parse_meta_cpa(row: dict, purchases: float) -> float:
    """Cost per result as Ads Manager shows it (website purchase when that's the result)."""
    reported = _first_insight_value(row.get("cost_per_result"))
    if reported > 0:
        return reported
    by_type: dict[str, float] = {}
    for item in row.get("cost_per_action_type") or []:
        action_type = str(item.get("action_type") or "")
        try:
            by_type[action_type] = float(item.get("value") or 0)
        except (TypeError, ValueError):
            continue
    for action_type in _ADS_MANAGER_PURCHASE_COST_TYPES:
        value = by_type.get(action_type) or 0.0
        if value > 0:
            return value
    for action_type, value in by_type.items():
        if action_type.endswith("purchase") and value > 0:
            return value
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


def _meta_json(resp: httpx.Response) -> dict:
    try:
        payload = resp.json()
    except Exception:
        payload = {"error": {"message": resp.text[:400]}}
    if not isinstance(payload, dict):
        payload = {"error": {"message": str(payload)[:400]}}
    if resp.status_code >= 400:
        err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        message = err.get("message") or resp.text[:400] or f"Meta API {resp.status_code}"
        raise RuntimeError(message)
    return payload
