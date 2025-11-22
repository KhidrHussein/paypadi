"""
Paystack payment gateway implementation.
"""
import json
import requests
from decimal import Decimal
from typing import Dict, Optional, Any
from django.conf import settings
from django.urls import reverse

class PaystackGateway:
    """Paystack payment gateway implementation."""
    
    def __init__(self, test_mode=None, **kwargs):
        """Initialize the Paystack gateway."""
        self.test_mode = getattr(settings, 'PAYSTACK_TEST_MODE', True) if test_mode is None else test_mode
        self.secret_key = (
            getattr(settings, 'PAYSTACK_SECRET_KEY')
            if not self.test_mode
            else getattr(settings, 'PAYSTACK_TEST_SECRET_KEY')
        )
        self.public_key = (
            getattr(settings, 'PAYSTACK_PUBLIC_KEY')
            if not self.test_mode
            else getattr(settings, 'PAYSTACK_TEST_PUBLIC_KEY')
        )
        self.base_url = 'https://api.paystack.co'
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }

    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make a request to the Paystack API."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('message', str(e))
                except ValueError:
                    error_message = e.response.text or str(e)
            return {
                'status': False,
                'message': f'Paystack API error: {error_message}'
            }

    def initialize_payment(
        self,
        amount: Decimal,
        email: str,
        reference: str,
        callback_url: str = None,
        metadata: Optional[Dict] = None,
        **kwargs
    ) -> Dict:
        """Initialize a payment request."""
        amount_in_kobo = int(amount * 100)  # Paystack uses kobo (multiply by 100)
        
        data = {
            'email': email,
            'amount': str(amount_in_kobo),
            'reference': reference,
            'callback_url': callback_url,
            'metadata': metadata or {}
        }
        
        # Add any additional parameters
        data.update(kwargs)
        
        response = self._make_request('POST', '/transaction/initialize', data)
        
        if response.get('status'):
            return {
                'status': True,
                'message': 'Payment initialized successfully',
                'data': {
                    'authorization_url': response['data']['authorization_url'],
                    'access_code': response['data']['access_code'],
                    'reference': response['data']['reference']
                }
            }
        return response

    def verify_payment(self, reference: str) -> Dict:
        """Verify a payment using the transaction reference."""
        response = self._make_request('GET', f'/transaction/verify/{reference}')
        
        if response.get('status') and response['data']['status'] == 'success':
            amount = Decimal(response['data']['amount']) / 100  # Convert back from kobo
            return {
                'status': True,
                'message': 'Payment verified',
                'data': {
                    'reference': response['data']['reference'],
                    'amount': amount,
                    'status': 'success',
                    'paid_at': response['data']['paid_at'],
                    'metadata': response['data'].get('metadata', {})
                }
            }
        return response

    def transfer(
        self,
        amount: Decimal,
        recipient_code: str,
        reference: str,
        reason: str = None,
        **kwargs
    ) -> Dict:
        """Initiate a transfer to a recipient."""
        amount_in_kobo = int(amount * 100)
        
        data = {
            'source': 'balance',
            'amount': amount_in_kobo,
            'recipient': recipient_code,
            'reference': reference,
            'reason': reason or 'Transfer',
        }
        
        # Add any additional parameters
        data.update(kwargs)
        
        return self._make_request('POST', '/transfer', data)

    def create_transfer_recipient(
        self,
        type: str,
        name: str,
        account_number: str,
        bank_code: str,
        currency: str = 'NGN',
        **kwargs
    ) -> Dict:
        """Create a transfer recipient."""
        data = {
            'type': type,  # nuban, mobile_money, etc.
            'name': name,
            'account_number': account_number,
            'bank_code': bank_code,
            'currency': currency,
        }
        
        # Add any additional parameters
        data.update(kwargs)
        
        return self._make_request('POST', '/transferrecipient', data)

    def verify_bank_account(self, account_number: str, bank_code: str) -> Dict:
        """Verify a bank account number."""
        return self._make_request(
            'GET',
            f'/bank/resolve?account_number={account_number}&bank_code={bank_code}'
        )

    def list_banks(self, country: str = 'nigeria') -> Dict:
        """List all supported banks."""
        return self._make_request('GET', f'/bank?country={country}')

    def handle_webhook(self, payload: Dict, signature: str = None) -> Dict:
        """Handle Paystack webhook."""
        if signature:
            # Verify the webhook signature if needed
            pass
            
        event = payload.get('event', '')
        data = payload.get('data', {})
        
        if event == 'charge.success':
            return {
                'status': True,
                'event': event,
                'data': {
                    'reference': data.get('reference'),
                    'amount': Decimal(data.get('amount', 0)) / 100,
                    'status': 'success',
                    'metadata': data.get('metadata', {})
                }
            }
        elif event == 'transfer.success':
            return {
                'status': True,
                'event': event,
                'data': {
                    'reference': data.get('reference'),
                    'amount': Decimal(data.get('amount', 0)) / 100,
                    'status': 'success',
                    'recipient': data.get('recipient'),
                    'metadata': data.get('metadata', {})
                }
            }
            
        return {
            'status': False,
            'message': f'Unhandled event: {event}'
        }
