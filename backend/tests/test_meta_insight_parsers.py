"""Ads Manager columns use link-click CPC/CTR and website-purchase CPA, not all-clicks."""

from app.integrations.meta.client import (
    parse_meta_cpa,
    parse_meta_link_clicks,
    parse_meta_link_cpc,
    parse_meta_link_ctr,
)
from app.services.ads_service import AdsService


UK_INSIGHT = {
    "campaign_id": "uk",
    "campaign_name": "UK",
    "spend": "75.77",
    "impressions": "3548",
    "reach": "2986",
    "frequency": "1.19",
    "clicks": "157",
    "cpc": "0.48",
    "ctr": "4.42",
    "cpm": "21.36",
    "inline_link_clicks": "86",
    "inline_link_click_ctr": "2.42",
    "cost_per_inline_link_click": "0.88",
    "website_ctr": [{"action_type": "link_click", "value": "2.42"}],
    "actions": [
        {"action_type": "omni_purchase", "value": "1"},
        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "1"},
    ],
    "action_values": [
        {"action_type": "omni_purchase", "value": "18.72"},
    ],
    "purchase_roas": [{"action_type": "omni_purchase", "value": "0.25"}],
    "cost_per_action_type": [
        {"action_type": "omni_purchase", "value": "75.77"},
        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "75.77"},
    ],
}

CA_INSIGHT = {
    "campaign_id": "ca",
    "campaign_name": "CA -English",
    "spend": "44.93",
    "impressions": "3121",
    "reach": "2516",
    "frequency": "1.24",
    "clicks": "174",
    "cpc": "0.26",
    "ctr": "5.58",
    "cpm": "14.40",
    "inline_link_clicks": "99",
    "inline_link_click_ctr": "3.17",
    "cost_per_inline_link_click": "0.45",
    "website_ctr": [{"action_type": "link_click", "value": "3.17"}],
    "actions": [
        {"action_type": "omni_purchase", "value": "3"},
        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "3"},
    ],
    "action_values": [
        {"action_type": "omni_purchase", "value": "29.98"},
    ],
    "purchase_roas": [{"action_type": "omni_purchase", "value": "0.67"}],
    "cost_per_action_type": [
        {"action_type": "omni_purchase", "value": "14.98"},
        {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "15.85"},
    ],
    "cost_per_result": [
        {
            "indicator": "cost_per_action_type:offsite_conversion.fb_pixel_purchase",
            "values": [{"value": "15.85"}],
        }
    ],
}


def test_uk_row_matches_ads_manager_link_metrics():
    clicks = parse_meta_link_clicks(UK_INSIGHT)
    assert clicks == 86
    assert round(parse_meta_link_cpc(UK_INSIGHT, 75.77, clicks), 2) == 0.88
    assert round(parse_meta_link_ctr(UK_INSIGHT, 3548), 2) == 2.42


def test_ca_row_matches_ads_manager_link_metrics():
    clicks = parse_meta_link_clicks(CA_INSIGHT)
    assert clicks == 99
    assert round(parse_meta_link_cpc(CA_INSIGHT, 44.93, clicks), 2) == 0.45
    assert round(parse_meta_link_ctr(CA_INSIGHT, 3121), 2) == 3.17


def test_cpa_prefers_ads_manager_website_purchase_cost():
    row = {
        "spend": "44.93",
        "cost_per_action_type": [
            {"action_type": "omni_purchase", "value": "14.98"},
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "15.85"},
        ],
    }
    assert round(parse_meta_cpa(row, 3), 2) == 15.85


def test_cpa_uses_cost_per_result_when_present():
    assert round(parse_meta_cpa(CA_INSIGHT, 3), 2) == 15.85


def test_link_cpc_falls_back_to_spend_over_link_clicks():
    row = {"spend": "75.77", "inline_link_clicks": "86", "cpc": "0.48"}
    clicks = parse_meta_link_clicks(row)
    assert round(parse_meta_link_cpc(row, 75.77, clicks), 2) == 0.88


def test_performance_table_row_matches_ads_manager_screenshot():
    svc = AdsService()
    uk = svc._summarize_insight_row(UK_INSIGHT, name_keys=("campaign_name",))
    ca = svc._summarize_insight_row(CA_INSIGHT, name_keys=("campaign_name",))
    assert (uk["cpc"], uk["ctr"], uk["cpa"], uk["spend"]) == (0.88, 2.42, 75.77, 75.77)
    assert (ca["cpc"], ca["ctr"], ca["cpa"], ca["spend"]) == (0.45, 3.17, 15.85, 44.93)
    assert uk["purchases"] == 1
    assert ca["purchases"] == 3
