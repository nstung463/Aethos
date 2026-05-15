"""Pydantic schemas for payment resources."""

from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    plan_id: str
    success_url: str
    cancel_url: str
