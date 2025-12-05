from django.test import TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User, UserProfile
from users.views import UserRegistrationView

class RegistrationReproductionTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = '/api/v1/auth/register/'
        self.phone_number = '+2348114189157'  # Example phone number
        
    def test_duplicate_profile_creation_crash(self):
        """
        Test that registration crashes with 500 due to duplicate UserProfile creation.
        """
        # Simulate verified phone in session
        session = self.client.session
        session['phone_verified'] = True
        session['verified_phone'] = self.phone_number
        session.save()
        
        data = {
            # phone_number is taken from session if not provided, or can be provided
            "password": "123456",
            "role": "rider",
            "first_name": "Test",
            "last_name": "User"
        }
        
        # We expect a 500 error currently
        try:
            response = self.client.post(self.url, data, format='json')
            
            print(f"Response status: {response.status_code}")
            if response.status_code == 500:
                print("Successfully reproduced 500 error!")
            else:
                print(f"Failed to reproduce. Status: {response.status_code}")
                print(f"Response data: {response.data}")
                
            # Check if user was created despite the crash (transaction should roll back)
            user_exists = User.objects.filter(phone_number=self.phone_number).exists()
            print(f"User exists in DB: {user_exists}")
            
            # Check if profile exists
            if user_exists:
                profile_exists = UserProfile.objects.filter(user__phone_number=self.phone_number).exists()
                print(f"Profile exists in DB: {profile_exists}")

        except Exception as e:
            print(f"Exception caught: {e}")

