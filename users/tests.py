from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from users.models import User

class TransactionPinTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number='+2348012345678',
            password='testpassword'
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse('set-transaction-pin')

    def test_set_new_pin(self):
        """Test setting a new PIN when none exists"""
        data = {
            "new_pin": "1234",
            "confirm_pin": "1234"
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_transaction_pin("1234"))

    def test_update_existing_pin(self):
        """Test updating an existing PIN"""
        # First set a PIN
        self.user.set_transaction_pin("1234")
        self.user.save()
        
        # Now update it
        data = {
            "current_pin": "1234",
            "new_pin": "5678",
            "confirm_pin": "5678"
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_transaction_pin("5678"))
        self.assertFalse(self.user.check_transaction_pin("1234"))

    def test_update_pin_incorrect_current(self):
        """Test updating PIN with wrong current PIN"""
        self.user.set_transaction_pin("1234")
        self.user.save()
        
        data = {
            "current_pin": "0000",
            "new_pin": "5678",
            "confirm_pin": "5678"
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('current_pin', response.data)
