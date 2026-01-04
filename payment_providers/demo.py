"""Demo payment provider for testing without real payment gateway."""

import uuid
import logging
from typing import Dict, Any, Optional

from .base import PaymentProvider, PaymentResult, SubscriptionResult


logger = logging.getLogger(__name__)


class DemoPaymentProvider(PaymentProvider):
    """Demo payment provider that simulates payments without real transactions."""
    
    def __init__(self, bot_username: str = "your_bot"):
        """Initialize demo provider.
        
        Args:
            bot_username: Telegram bot username for redirect URLs
        """
        self.bot_username = bot_username
        self.payments = {}  # Store demo payments
        self.subscriptions = {}  # Store demo subscriptions
        
    async def create_payment(
        self,
        user_id: int,
        amount: float,
        currency: str = "USD",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> PaymentResult:
        """Create a demo one-time payment."""
        payment_id = f"demo_pay_{uuid.uuid4().hex[:16]}"
        
        self.payments[payment_id] = {
            'user_id': user_id,
            'amount': amount,
            'currency': currency,
            'description': description,
            'status': 'pending',
            'metadata': metadata or {}
        }
        
        payment_url = f"https://t.me/{self.bot_username}?start=demo_pay_{payment_id}"
        
        logger.info(f"Demo payment created: {payment_id} for user {user_id}, amount {amount} {currency}")
        
        return PaymentResult(
            success=True,
            payment_url=payment_url,
            payment_id=payment_id,
            metadata={'demo': True, 'instructions': 'Use /demo_complete command to simulate payment'}
        )
    
    async def create_subscription(
        self,
        user_id: int,
        amount: float,
        currency: str = "USD",
        interval: str = "month",
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> PaymentResult:
        """Create a demo recurring subscription."""
        subscription_id = f"demo_sub_{uuid.uuid4().hex[:16]}"
        
        self.subscriptions[subscription_id] = {
            'user_id': user_id,
            'amount': amount,
            'currency': currency,
            'interval': interval,
            'description': description,
            'status': 'pending',
            'metadata': metadata or {}
        }
        
        payment_url = f"https://t.me/{self.bot_username}?start=demo_sub_{subscription_id}"
        
        logger.info(f"Demo subscription created: {subscription_id} for user {user_id}, {amount} {currency}/{interval}")
        
        return PaymentResult(
            success=True,
            payment_url=payment_url,
            payment_id=subscription_id,
            metadata={'demo': True, 'instructions': 'Use /demo_complete command to simulate payment'}
        )
    
    async def cancel_subscription(
        self,
        subscription_id: str,
        reason: Optional[str] = None
    ) -> SubscriptionResult:
        """Cancel a demo subscription."""
        if subscription_id in self.subscriptions:
            self.subscriptions[subscription_id]['status'] = 'cancelled'
            logger.info(f"Demo subscription cancelled: {subscription_id}, reason: {reason}")
            return SubscriptionResult(success=True, subscription_id=subscription_id)
        
        return SubscriptionResult(
            success=False,
            error=f"Subscription {subscription_id} not found"
        )
    
    async def verify_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """Demo webhook verification always returns True."""
        return True
    
    async def process_webhook(
        self,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process demo webhook notification."""
        payment_id = payload.get('payment_id')
        
        if payment_id in self.payments:
            self.payments[payment_id]['status'] = 'completed'
            return {'success': True, 'type': 'payment', 'payment_id': payment_id}
        
        if payment_id in self.subscriptions:
            self.subscriptions[payment_id]['status'] = 'active'
            return {'success': True, 'type': 'subscription', 'subscription_id': payment_id}
        
        return {'success': False, 'error': 'Payment not found'}
    
    async def complete_demo_payment(self, payment_id: str) -> Dict[str, Any]:
        """Manually complete a demo payment (for testing)."""
        if payment_id in self.payments:
            self.payments[payment_id]['status'] = 'completed'
            return {'success': True, 'payment': self.payments[payment_id]}
        
        if payment_id in self.subscriptions:
            self.subscriptions[payment_id]['status'] = 'active'
            return {'success': True, 'subscription': self.subscriptions[payment_id]}
        
        return {'success': False, 'error': 'Payment not found'}
