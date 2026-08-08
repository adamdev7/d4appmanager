from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    status: str
    description: str
    at: str


class TrackOrderLineItem(BaseModel):
    title: str
    variant: str = ""
    quantity: int = 1
    image_url: str = ""
    price: str = ""


class TrackOrderResponse(BaseModel):
    order_number: str
    order_placed_at: str | None = None
    order_total: str | None = None
    currency: str | None = None
    line_items: list[TrackOrderLineItem] = Field(default_factory=list)
    tracking_number: str | None = None
    carrier: str | None = None
    status: str
    shipped: bool = False
    status_label: str = "Not shipped yet"
    message: str = "Your order has been placed and is being prepared. It has not shipped yet."
    timeline: list[TimelineEvent] = Field(default_factory=list)
    last_updated_at: str | None = None
