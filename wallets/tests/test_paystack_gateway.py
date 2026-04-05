import json
from decimal import Decimal
from django.test import TestCase
from unittest.mock import patch, MagicMock
from wallets.payment_gateways.paystack import PaystackGateway

class PaystackGatewayTest(TestCase):
    def setUp(self):
        # We enforce test_mode to avoid needing real API keys during testing
        self.gateway = PaystackGateway(test_mode=True)
        # Mock self.gateway.secret_key to avoid NoneType errors if settings missing
        self.gateway.secret_key = 'sk_test_fake_key'

    @patch.object(PaystackGateway, '_make_request')
    def test_transfer_funds_orchestration(self, mock_make_request):
        """
        Verify that transfer_funds correctly routes API requests sequentially to Paystack:
        1. Resolve account (GET /bank/resolve)
        2. Create transfer recipient (POST /transferrecipient)
        3. Initiate Transfer (POST /transfer)
        """
        # We need _make_request to return different things based on the endpoint called
        def side_effect(method, endpoint, data=None):
            if 'bank/resolve' in endpoint:
                return {
                    'status': True,
                    'message': 'Account resolved',
                    'data': {'account_name': 'JOHN DOE'}
                }
            elif 'transferrecipient' in endpoint:
                # Ensure the name was correctly resolved and passed
                self.assertEqual(data['name'], 'JOHN DOE')
                self.assertEqual(data['account_number'], '0123456789')
                self.assertEqual(data['bank_code'], '058')
                return {
                    'status': True,
                    'message': 'Recipient created',
                    'data': {'recipient_code': 'RCP_123456789'}
                }
            elif '/transfer' in endpoint:
                # Ensure the recipient code and correct amount was routed safely
                self.assertEqual(data['recipient'], 'RCP_123456789')
                self.assertEqual(data['amount'], 500000) # 5000 * 100 kobo
                self.assertEqual(data['reference'], 'TEST-REF-123')
                return {
                    'status': True,
                    'message': 'Transfer successful',
                    'data': {
                        'reference': 'TEST-REF-123',
                        'status': 'success',
                        'amount': 500000
                    }
                }
            return {'status': False, 'message': 'Unknown endpoint'}

        mock_make_request.side_effect = side_effect

        result = self.gateway.transfer_funds(
            amount=Decimal('5000.00'),
            recipient_account='0123456789',
            recipient_bank_code='058',
            reference='TEST-REF-123',
            narration='Test Withdrawal Payout'
        )

        # Assert final result cascades up properly
        self.assertTrue(result['status'])
        self.assertEqual(result['data']['status'], 'success')
        self.assertEqual(result['data']['reference'], 'TEST-REF-123')
        
        # Verify exactly 3 network calls were made in sequence
        self.assertEqual(mock_make_request.call_count, 3)
