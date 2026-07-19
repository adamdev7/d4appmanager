import enum


class AutomationEventType(str, enum.Enum):
    """Internal automation events (mapped from Shopify webhooks)."""

    ORDER_PAID = "ORDER_PAID"
    ORDER_FULFILLED = "ORDER_FULFILLED"
    ORDER_DELIVERED = "ORDER_DELIVERED"
    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    FIRST_PURCHASE = "FIRST_PURCHASE"
    REPEAT_PURCHASE = "REPEAT_PURCHASE"
    TRACKING_ADDED = "TRACKING_ADDED"
    IN_TRANSIT_UPDATE = "IN_TRANSIT_UPDATE"


# Shopify webhook topic -> internal event(s)
_TOPIC_EVENT_MAP: dict[str, list[AutomationEventType]] = {
    "orders/paid": [AutomationEventType.ORDER_PAID],
    "orders/fulfilled": [AutomationEventType.ORDER_FULFILLED],
    "customers/create": [AutomationEventType.CUSTOMER_CREATED],
    "fulfillments/create": [AutomationEventType.TRACKING_ADDED],
}


def derive_automation_events(topic: str, payload: dict) -> list[AutomationEventType]:
    """Map a Shopify webhook topic + payload to zero or more automation events."""
    events: list[AutomationEventType] = list(_TOPIC_EVENT_MAP.get(topic, []))

    if topic == "orders/create":
        customer = payload.get("customer") or {}
        orders_count = customer.get("orders_count")
        if orders_count == 1:
            events.append(AutomationEventType.FIRST_PURCHASE)
        elif isinstance(orders_count, int) and orders_count > 1:
            events.append(AutomationEventType.REPEAT_PURCHASE)

    if topic == "fulfillments/update":
        shipment = (payload.get("shipment_status") or "").lower()
        if shipment == "delivered":
            events.append(AutomationEventType.ORDER_DELIVERED)
        elif shipment in ("in_transit", "out_for_delivery"):
            events.append(AutomationEventType.IN_TRANSIT_UPDATE)
        tracking = payload.get("tracking_number") or payload.get("tracking_numbers")
        if tracking and AutomationEventType.TRACKING_ADDED not in events:
            events.append(AutomationEventType.TRACKING_ADDED)

    seen: set[AutomationEventType] = set()
    unique: list[AutomationEventType] = []
    for ev in events:
        if ev not in seen:
            seen.add(ev)
            unique.append(ev)
    return unique
