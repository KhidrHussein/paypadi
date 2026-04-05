from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from users.models import User, OTP
from django.contrib.sessions.backends.db import SessionStore

class RegistrationSessionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.otp_verify_url = reverse('otp-verify')
        self.register_url = reverse('user-register')
        self.phone_number = '+2348141983088'

    def test_registration_with_session_id(self):
        """Test that registration works when passing session_id in the body."""
        # 1. Create a valid OTP
        otp_code = "123456"
        purpose = "registration"
        OTP.objects.create(
            phone_number=self.phone_number,
            code=otp_code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=5)
        )

        # 2. Verify OTP and get session_id
        verify_data = {
            "phone_number": self.phone_number,
            "code": otp_code,
            "purpose": purpose
        }
        verify_response = self.client.post(self.otp_verify_url, verify_data)
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        session_id = verify_response.data.get('session_id')
        self.assertIsNotNone(session_id)

        # 3. Simulate a NEW client (no cookies) but providing session_id
        new_client = APIClient()
        register_data = {
            "phone_number": self.phone_number,
            "password": "123456",
            "first_name": "Test",
            "last_name": "User",
            "session_id": session_id
        }
        
        # Registration should succeed
        response = new_client.post(self.register_url, register_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['phone_number'], self.phone_number)

    def test_registration_fails_with_invalid_session_id(self):
        """Test that registration fails with an invalid session_id."""
        register_data = {
            "phone_number": self.phone_number,
            "password": "123456",
            "first_name": "Test",
            "last_name": "User",
            "session_id": "invalid-session-key"
        }
        
        response = self.client.post(self.register_url, register_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], "Phone number not verified")
