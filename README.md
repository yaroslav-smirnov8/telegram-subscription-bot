# Telegram Subscription Bot

**Type:** Telegram Bot with Payment Integration

A flexible, open-source Telegram bot for managing subscriptions with pluggable payment providers.

## Platform & Runtime Requirements

This is a **Telegram Bot** for community monetization. It is platform-dependent and requires external services.

**Core Dependencies:**
- Telegram Bot API (bot token required)
- MySQL 5.7+ database with ACID transaction support
- Payment provider: Stripe, YooKassa, or other HTTPS-accessible API
- Python 3.8+ with asyncio runtime

**Why local execution without external services is not applicable:**
- Telegram Bot API requires valid bot token and network connectivity
- Database requires MySQL instance (local Docker or remote)
- Payment provider credentials (API keys, webhook signing keys) required for payment flows
- Webhook endpoints for payment provider callbacks must be internet-accessible

This is standard for monetized Telegram systems. The architecture assumes production payment infrastructure.

## Features

- 🔌 **Pluggable Payment Providers** - Easy integration with any payment gateway
- 🎭 **Demo Mode** - Test all features without real payments
- 🔄 **Subscription Management** - Recurring payments and auto-renewal
- 👥 **Group Access Control** - Automatic member management based on subscription status
- 🌍 **International** - Support for multiple currencies and payment providers
- 🔒 **Secure** - Webhook signature verification and secure payment handling

## Quick Start

### 1. Installation

```bash
git clone <repository-url>
cd pbot
pip install -r requirements.txt
```

### 2. Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:
```env
TELEGRAM_API_TOKEN=your_bot_token
BOT_USERNAME=your_bot_username
TELEGRAM_GROUP_ID=your_group_id
PAYMENT_PROVIDER=demo
```

### 3. Run in Demo Mode

```bash
python bot.py
```

The bot will run in demo mode - all features work, but no real payments are processed.

## Payment Providers

### Demo Provider (Default)

Perfect for development and testing. Simulates all payment operations without real transactions.

**Features:**
- No configuration needed
- Test all bot features
- Simulate successful/failed payments
- No external dependencies

### Stripe Integration

To use Stripe:

1. Install Stripe SDK:
```bash
pip install stripe
```

2. Get API keys from [Stripe Dashboard](https://dashboard.stripe.com/apikeys)

3. Configure `.env`:
```env
PAYMENT_PROVIDER=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

4. Uncomment Stripe provider in `config.py`:
```python
elif provider_type == 'stripe':
    from payment_providers.stripe_example import StripePaymentProvider
    return StripePaymentProvider()
```

5. Complete implementation in `payment_providers/stripe_example.py`

### Adding Custom Providers

Create a new provider by implementing the `PaymentProvider` interface:

```python
# payment_providers/your_provider.py
from .base import PaymentProvider, PaymentResult, SubscriptionResult

class YourPaymentProvider(PaymentProvider):
    async def create_payment(self, user_id, amount, currency, ...):
        # Your implementation
        pass
    
    async def create_subscription(self, user_id, amount, ...):
        # Your implementation
        pass
    
    # Implement other required methods...
```

Then register it in `config.py`:

```python
elif provider_type == 'your_provider':
    from payment_providers.your_provider import YourPaymentProvider
    return YourPaymentProvider()
```

## Bot Commands

### User Commands
- `/start` - Start interaction with the bot
- `/subscribe` - Subscribe to the service
- `/status` - Check subscription status
- `/cancel` - Cancel auto-renewal

### Admin Commands
- `/set_price [amount]` - Set subscription price

## Architecture

```
pbot/
├── payment_providers/          # Payment provider implementations
│   ├── base.py                # Abstract base class
│   ├── demo.py                # Demo provider (default)
│   ├── stripe_example.py      # Stripe example
│   └── __init__.py
├── bot.py                     # Main bot logic
├── config.py                  # Configuration and provider setup
├── db.py                      # Database operations
└── .env                       # Environment configuration
```

## Database

Uses SQLite by default. The database stores:
- User subscriptions
- Payment history
- Auto-renewal settings
- Group membership status

## Webhook Setup

For production deployment:

1. Set up HTTPS endpoint
2. Configure webhook URL in your payment provider dashboard
3. Update `WEBHOOK_HOST` and `WEBHOOK_PORT` in `.env`

## Development

### Testing Demo Mode

```bash
# Start bot
python bot.py

# In Telegram:
/start
/subscribe

# Simulate payment completion:
/demo_complete [payment_id]
```

### Adding New Features

1. Extend `PaymentProvider` base class if needed
2. Implement in your provider
3. Update bot logic in `bot.py`
4. Test in demo mode first

## Deployment

### Docker (Recommended)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
```

### Systemd Service

```ini
[Unit]
Description=Telegram Subscription Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/path/to/pbot
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Security

- Never commit `.env` file
- Use environment variables for secrets
- Verify webhook signatures
- Use HTTPS for webhooks
- Regularly update dependencies

## Contributing

Contributions welcome! To add a new payment provider:

1. Create provider class in `payment_providers/`
2. Implement all abstract methods
3. Add configuration example
4. Update documentation
5. Submit pull request

## What to Review Instead of Running Locally

Best understood through code review and design analysis:

### Payment Architecture (Adapter Pattern)
- **Provider Interface Design** (`/payment_providers/base.py`) – Abstract base class defining payment provider contract
- **Stripe Implementation** (`/payment_providers/stripe_adapter.py`) – Stripe integration with webhook signature verification
- **Regional Provider Support** – How different providers implement the same interface
- **Demo Provider** – Testing adapter allowing zero-config integration testing

### Subscription State Machine
- **Lifecycle States** – pending → active → grace_period → expired → canceled transitions
- **Automatic Renewals** – Background job checking expiring subscriptions and auto-charging
- **Failed Payment Recovery** – Grace period logic and retry notifications

### Telegram Integration
- **Group Membership Management** – Adding/removing users from Telegram groups atomically with subscription updates
- **Webhook Callbacks** – Bot receiving payment confirmations and triggering membership changes
- **User Session Management** – Stateless conversation flows for subscription selection

### Webhook Reliability
- **Signature Verification** – HMAC validation preventing replay attacks
- **Idempotency Handling** – Database tracking of processed webhooks prevents duplicate charges
- **Atomic Updates** – Transactions ensuring payment confirmation and membership change together

### Data Integrity & Concurrency
- **Race Condition Prevention** – Pessimistic locking on subscription updates during concurrent payment processing
- **Transaction Safety** – ACID guarantees preventing partial writes
- **User-Provider Mapping** – Preventing orphaned subscriptions and duplicate group access

## License

MIT License - feel free to use in your projects

## Support

- Issues: [GitHub Issues](your-repo/issues)
- Discussions: [GitHub Discussions](your-repo/discussions)

## Roadmap

- [ ] PayPal integration example
- [ ] Cryptocurrency payments
- [ ] Multiple subscription tiers
- [ ] Promo codes and discounts
- [ ] Analytics dashboard
- [ ] Multi-language support
