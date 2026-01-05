from django.test import TestCase
from unittest.mock import patch, MagicMock
from django.conf import settings
from core.sms import send_sms
from core.models import OTPManager
from users.models import OTP

class SMSTestCase(TestCase):
    @patch('core.sms.Client')
    def test_send_sms_success(self, mock_client):
        """Test sending SMS successfully."""
        # Setup mock
        mock_messages = MagicMock()
        mock_client.return_value.messages = mock_messages
        
        # Configure settings
        with self.settings(
            TWILIO_ACCOUNT_SID='ACtest',
            TWILIO_AUTH_TOKEN='token',
            TWILIO_PHONE_NUMBER='+1234567890'
        ):
            # Call function
            result = send_sms(' +2348012345678', 'Test message')
            
            # Verify
            self.assertTrue(result)
            mock_client.assert_called_with('ACtest', 'token')
            mock_messages.create.assert_called_with(
                body='Test message',
                from_='+1234567890',
                to=' +2348012345678'
            )

    @patch('core.sms.Client')
    def test_send_sms_missing_credentials(self, mock_client):
        """Test sending SMS with missing credentials."""
        with self.settings(TWILIO_ACCOUNT_SID=''):
            result = send_sms('+2348012345678', 'Test message')
            self.assertFalse(result)
            mock_client.assert_not_called()

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
