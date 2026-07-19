"""Carrier tracking APIs (17TRACK, YunExpress) with per-store credentials."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.tracking.credentials import CarrierConfig
from app.tracking.payload_parser import map_shipment_status_to_tracking_status, timeline_event
from app.tracking.timeline_normalize import event_status_from_description, normalize_timeline

logger = logging.getLogger(__name__)


def _map_17track_main_status(code: str | int | None, *, sub_status: str | None = None) -> str:
    """Map 17TRACK v2.2 status strings (e.g. Delivered) or legacy numeric codes."""
    for candidate in (code, sub_status):
        if candidate is None:
            continue
        if isinstance(candidate, str):
            normalized = candidate.strip().lower().replace("_", "").replace(" ", "")
            if not normalized:
                continue
            if "delivered" in normalized:
                return "delivered"
            if normalized in (
                "intransit",
                "outfordelivery",
                "availableforpickup",
                "inforeceived",
            ) or normalized.startswith("intransit"):
                return "in_transit"
            if normalized in ("outfordelivery", "availableforpickup"):
                return "in_transit"
            if normalized.isdigit():
                code = int(normalized)
                break
            continue
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            continue
        if value in (40, 50):
            return "delivered"
        if value in (10, 20, 30, 35):
            return "in_transit"
    return "pending"


def _map_17track_event_status(stage: str | None, sub_status: str | None = None) -> str:
    return _map_17track_main_status(stage, sub_status=sub_status)


async def _register_17track(api_key: str, tracking_number: str, carrier: str | None) -> None:
    body: list[dict[str, str]] = [{"number": tracking_number}]
    if carrier:
        body[0]["carrier"] = carrier
    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(
            "https://api.17track.net/track/v2.2/register",
            headers={"17token": api_key, "Content-Type": "application/json"},
            json=body,
        )


async def fetch_17track(
    config: CarrierConfig,
    tracking_number: str,
    carrier: str | None = None,
) -> dict[str, Any] | None:
    api_key = config.track17_api_key
    if not api_key or not tracking_number:
        return None

    body: list[dict[str, str]] = [{"number": tracking_number}]
    if carrier:
        body[0]["carrier"] = carrier

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.17track.net/track/v2.2/gettrackinfo",
                headers={"17token": api_key, "Content-Type": "application/json"},
                json=body,
            )
            if resp.status_code != 200:
                logger.warning("17TRACK HTTP %s for %s", resp.status_code, tracking_number)
                return None
            data = resp.json()
    except Exception:
        logger.exception("17TRACK request failed for %s", tracking_number)
        return None

    accepted = (data.get("data") or {}).get("accepted") or []
    if not accepted:
        try:
            await _register_17track(api_key, tracking_number, carrier)
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.17track.net/track/v2.2/gettrackinfo",
                    headers={"17token": api_key, "Content-Type": "application/json"},
                    json=body,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    accepted = (data.get("data") or {}).get("accepted") or []
        except Exception:
            logger.exception("17TRACK register/retry failed for %s", tracking_number)

    if not accepted:
        rejected = (data.get("data") or {}).get("rejected") or []
        if rejected:
            err = rejected[0].get("error") or rejected[0]
            logger.info("17TRACK rejected %s: %s", tracking_number, err)
        return None

    track = accepted[0].get("track_info") or {}
    latest = track.get("latest_status") or {}
    main_status_raw = latest.get("status")
    sub_status_raw = latest.get("sub_status")
    status = _map_17track_main_status(main_status_raw, sub_status=sub_status_raw)

    events: list[dict[str, str]] = []
    for provider in track.get("tracking", {}).get("providers") or []:
        provider_name = (provider.get("provider") or {}).get("name") or ""
        for event in provider.get("events") or []:
            description = (event.get("description") or event.get("stage") or "Update").strip()
            location = (event.get("location") or "").strip()
            if location:
                description = f"{description} ({location})"
            if provider_name and provider_name not in description:
                description = f"{description} — {provider_name}"
            at_raw = event.get("time_iso") or event.get("time_utc") or event.get("time")
            at = datetime.now(UTC)
            if at_raw:
                try:
                    at = datetime.fromisoformat(str(at_raw).replace("Z", "+00:00"))
                except ValueError:
                    pass
            event_status = _map_17track_event_status(
                event.get("stage") or event.get("sub_status"),
                sub_status=event.get("sub_status"),
            )
            events.append(timeline_event(event_status, description, at=at))

    latest_event = track.get("latest_event") or {}
    if latest_event:
        desc = (latest_event.get("description") or latest_event.get("stage") or "").strip()
        if desc:
            at_raw = latest_event.get("time_iso") or latest_event.get("time_utc")
            at = datetime.now(UTC)
            if at_raw:
                try:
                    at = datetime.fromisoformat(str(at_raw).replace("Z", "+00:00"))
                except ValueError:
                    pass
            ev_status = _map_17track_event_status(
                latest_event.get("stage") or latest_event.get("sub_status"),
                sub_status=latest_event.get("sub_status"),
            )
            latest_row = timeline_event(ev_status, desc, at=at)
            existing_desc = {e.get("description", "").strip().lower() for e in events}
            if desc.strip().lower() not in existing_desc:
                events.append(latest_row)

    status_descr = latest.get("sub_status_descr") or latest.get("status_description")
    if not events and status_descr:
        events.append(
            timeline_event(status, str(status_descr), at=datetime.now(UTC))
        )

    # Prefer latest event stage if main status mapping still pending but events show delivered
    if status == "pending" and events:
        for ev in reversed(events):
            if ev.get("status") == "delivered":
                status = "delivered"
                break
            if ev.get("status") == "in_transit":
                status = "in_transit"
                break

    carrier_name = carrier
    if not carrier_name:
        providers = track.get("tracking", {}).get("providers") or []
        if providers:
            carrier_name = (providers[0].get("provider") or {}).get("name")

    return {
        "status": status,
        "carrier": carrier_name or "",
        "events": normalize_timeline(events, shipment_status=status),
        "last_updated_at": datetime.now(UTC).isoformat(),
        "source": "17track",
        "carrier_status_raw": str(main_status_raw or ""),
        "carrier_sub_status_raw": str(sub_status_raw or ""),
    }


async def fetch_yunexpress(
    config: CarrierConfig,
    tracking_number: str,
) -> dict[str, Any] | None:
    api_key = config.yunexpress_api_key
    if not api_key or not tracking_number:
        return None

    base = config.yunexpress_api_url.rstrip("/")
    params: dict[str, str] = {"trackingNumber": tracking_number}
    if config.yunexpress_customer_code:
        params["customerCode"] = config.yunexpress_customer_code

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{base}/Track/GetTrackInfo",
                params=params,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if resp.status_code != 200:
                logger.warning("YunExpress HTTP %s for %s", resp.status_code, tracking_number)
                return None
            data = resp.json()
    except Exception:
        logger.exception("YunExpress request failed for %s", tracking_number)
        return None

    result = data.get("Result") or data.get("result") or data
    if not isinstance(result, dict):
        return None

    raw_status = str(result.get("Status") or result.get("status") or "").lower()
    if "deliver" in raw_status:
        status = "delivered"
    elif raw_status:
        status = "in_transit"
    else:
        status = "pending"

    events: list[dict[str, str]] = []
    for item in result.get("TrackPoints") or result.get("track_points") or []:
        desc = str(item.get("Description") or item.get("description") or "Update")
        at_raw = item.get("Time") or item.get("time")
        at = datetime.now(UTC)
        if at_raw:
            try:
                at = datetime.fromisoformat(str(at_raw).replace("Z", "+00:00"))
            except ValueError:
                pass
        event_status = event_status_from_description(desc, status)
        events.append(timeline_event(event_status, desc, at=at))

    return {
        "status": status,
        "carrier": "YunExpress",
        "events": normalize_timeline(events, shipment_status=status),
        "last_updated_at": datetime.now(UTC).isoformat(),
        "source": "yunexpress",
    }


async def enrich_from_carrier_apis(
    config: CarrierConfig,
    tracking_number: str,
    carrier: str | None,
) -> dict[str, Any] | None:
    if config.mode == "shopify_only":
        return None

    if config.mode == "yunexpress":
        return await fetch_yunexpress(config, tracking_number)

    if config.mode == "17track":
        return await fetch_17track(config, tracking_number, carrier)

    if config.should_use_yunexpress(carrier, tracking_number):
        result = await fetch_yunexpress(config, tracking_number)
        if result:
            return result

    if config.has_track17:
        return await fetch_17track(config, tracking_number, carrier)

    if config.has_yunexpress:
        return await fetch_yunexpress(config, tracking_number)

    return None
