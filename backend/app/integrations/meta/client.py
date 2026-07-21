"""Meta (Facebook) Marketing API client for ad insights."""

from __future__ import annotations

import httpx

META_GRAPH_VERSION = "v21.0"
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"


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
        time_increment: int = 1,
    ) -> dict:
        """Daily account-level insights."""
        return await self._fetch_insights(
            level="account",
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment=time_increment,
            breakdown_fields="spend,impressions,clicks,cpc,cpm,ctr,actions,action_values,purchase_roas",
        )

    async def get_campaign_insights(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        date_preset: str | None = None,
    ) -> list[dict]:
        """Campaign-level insights for the period."""
        data = await self._fetch_insights(
            level="campaign",
            since=since,
            until=until,
            date_preset=date_preset,
            time_increment="all_days",
            breakdown_fields=(
                "campaign_id,campaign_name,spend,impressions,clicks,cpc,cpm,ctr,"
                "actions,action_values,purchase_roas"
            ),
        )
        return list(data.get("data") or [])

    async def _fetch_insights(
        self,
        *,
        level: str,
        since: str | None,
        until: str | None,
        date_preset: str | None = None,
        time_increment: int | str,
        breakdown_fields: str,
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
        async with httpx.AsyncClient(timeout=60) as client:
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
