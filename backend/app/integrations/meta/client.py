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


def parse_meta_purchases(actions: list[dict] | None) -> float:
    for action_type in ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase"):
        count = parse_meta_actions(actions, action_type)
        if count > 0:
            return count
    return 0.0


def parse_meta_purchase_value(action_values: list[dict] | None) -> float:
    if not action_values:
        return 0.0
    for action_type in ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase"):
        for item in action_values:
            if item.get("action_type") == action_type:
                try:
                    return float(item.get("value") or 0)
                except (TypeError, ValueError):
                    return 0.0
    return 0.0
