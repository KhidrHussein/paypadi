from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User

class DebugAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='+2348012345678',
            password='testpassword'
        )
        self.url = '/api/v1/auth/jwt/token/'

    def test_login_user_not_found(self):
        """Test login to reproduce User not found error"""
        data = {
            "phone_number": "08012345678",
            "password": "testpassword"
        }
        print("\n--- Starting Test Request ---")
        try:
            response = self.client.post(self.url, data)
            print(f"Response Status: {response.status_code}")
            print(f"Response Data: {response.data}")
            if response.status_code != 200:
                print("Test Failed with status != 200")
        except Exception:
            import traceback
            traceback.print_exc()
            raise
        print("--- End Test Request ---\n")
