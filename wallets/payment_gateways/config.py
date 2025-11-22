"""
Payment gateway configuration settings.
"""
import os
from decimal import Decimal
from django.conf import settings

# Default payment gateway to use
PAYMENT_GATEWAY = getattr(settings, 'PAYMENT_GATEWAY', 'mock')

# Payment gateway settings
PAYMENT_GATEWAYS = {
    'mock': {
        'class': 'wallets.payment_gateways.MockPaymentGateway',
        'test_mode': True,
    },
    'paystack': {
        'class': 'wallets.payment_gateways.PaystackGateway',
        'test_mode': getattr(settings, 'PAYSTACK_TEST_MODE', True),
    },
}

# Transaction settings
TRANSACTION_FEE_PERCENTAGE = Decimal('0.015')  # 1.5% transaction fee
MINIMUM_TRANSFER_AMOUNT = Decimal('100.00')   # Minimum transfer amount in Naira
MAXIMUM_TRANSFER_AMOUNT = Decimal('5000000.00')  # Maximum transfer amount in Naira

# Webhook settings
WEBHOOK_SECRET = getattr(settings, 'PAYMENT_WEBHOOK_SECRET', 'your-webhook-secret-here')

# Bank transfer settings
BANK_TRANSFER_NARRATION = 'Paypadi Transfer - {reference}'

# Settlement settings
SETTLEMENT_BANK_ACCOUNT = {
    'account_number': getattr(settings, 'SETTLEMENT_ACCOUNT_NUMBER', ''),
    'bank_code': getattr(settings, 'SETTLEMENT_BANK_CODE', ''),
    'account_name': getattr(settings, 'SETTLEMENT_ACCOUNT_NAME', 'Paypadi')
}

def get_payment_gateway(gateway_name=None):
    """Get the configured payment gateway instance."""
    gateway_name = gateway_name or PAYMENT_GATEWAY
    gateway_config = PAYMENT_GATEWAYS.get(gateway_name, PAYMENT_GATEWAYS['mock'])
    
    # Import the gateway class
    module_path, class_name = gateway_config['class'].rsplit('.', 1)
    module = __import__(module_path, fromlist=[class_name])
    gateway_class = getattr(module, class_name)
    
    # Initialize the gateway with its config
    gateway_config = gateway_config.copy()
    gateway_config.pop('class', None)
    return gateway_class(**gateway_config)
