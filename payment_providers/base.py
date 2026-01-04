"""Base abstract class for payment providers."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class PaymentResult:
    """Result of payment creation."""
    success: bool
    payment_url: Optional[str] = None
    payment_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SubscriptionResult:
    """Result of subscription operation."""
    success: bool
    subscription_id: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PaymentProvider(ABC):
    """Abstract base class for payment providers."""
    
    @abstractmethod
    async def create_payment(
        self,
        user_id: int,
        amount: float,
        currency: str = "USD",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> PaymentResult:
        """Create a one-time payment."""
        pass
    
    @abstractmethod
    async def create_subscription(
        self,
        user_id: int,
        amount: float,
        currency: str = "USD",
        interval: str = "month",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> PaymentResult:
        """Create a recurring subscription payment."""
        pass
    
    @abstractmethod
    async def cancel_subscription(
        self,
        subscription_id: str,
        reason: Optional[str] = None
    ) -> SubscriptionResult:
        """Cancel an active subscription."""
        pass
    
    @abstractmethod
    async def verify_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """Verify webhook signature."""
        pass
    
    @abstractmethod
    async def process_webhook(
        self,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process webhook notification."""
        pass
