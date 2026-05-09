from django.test import TestCase
from unittest.mock import patch, MagicMock
from django.conf import settings
from core.sms import send_sms
from core.models import OTPManager
from users.models import OTP

class SMSTestCase(TestCase):
    @patch('core.sms.requests.post')
    def test_send_sms_success(self, mock_post):
        """Test sending SMS successfully."""
        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message_id": "12345", "message": "Successfully Sent", "balance": 9.0, "user": "Test User"}
        mock_post.return_value = mock_response
        
        # Configure settings
        with self.settings(
            TERMII_API_KEY='test_api_key',
            TERMII_SENDER_ID='Paypadi',
            TERMII_BASE_URL='https://api.ng.termii.com/api/sms/send'
        ):
            # Call function
            result = send_sms('+2348012345678', 'Test message')
            
            # Verify
            self.assertTrue(result)
            self.assertTrue(mock_post.called)
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['to'], '2348012345678')
            self.assertEqual(payload['sms'], 'Test message')
            self.assertEqual(payload['api_key'], 'test_api_key')

    @patch('core.sms.requests.post')
    def test_send_sms_missing_credentials(self, mock_post):
        """Test sending SMS with missing credentials."""
        with self.settings(TERMII_API_KEY=''):
            result = send_sms('+2348012345678', 'Test message')
            self.assertFalse(result)
            mock_post.assert_not_called()

    @patch('core.sms.send_sms')
    def test_otp_creation_sends_sms(self, mock_send_sms):
        """Test that creating an OTP sends an SMS."""
        phone_number = '+2348012345678'
        purpose = 'registration'
        
        OTPManager.create_otp(phone_number, purpose)
        
        # Verify SMS was sent
        self.assertTrue(mock_send_sms.called)
        args, _ = mock_send_sms.call_args
        self.assertEqual(args[0], phone_number)
        self.assertIn('Your Paypadi OTP is:', args[1])
