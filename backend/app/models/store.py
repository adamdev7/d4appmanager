from enum import Enum

from pydantic import BaseModel, Field


class StoreStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    PENDING = "pending"


class Store(BaseModel):
    id: str
    name: str
    domain: str
    status: StoreStatus = StoreStatus.DISCONNECTED
    plan: str = "Basic"
    timezone: str = "UTC"
    currency: str = "USD"


class StoreCreate(BaseModel):
    name: str
    domain: str = Field(description="myshopify.com domain placeholder")


class StoreSettingsUpdate(BaseModel):
    name: str | None = None
    timezone: str | None = None
    currency: str | None = None
