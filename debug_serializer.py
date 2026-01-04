import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'paypadi.settings')
django.setup()

from users.models import User
from users.jwt_serializers import CustomTokenObtainPairSerializer
from rest_framework.exceptions import ValidationError

print("Using standalone script to debug Serializer...")

try:
    # 1. Ensure user exists
    phone = '+2348012345678'
    if not User.objects.filter(phone_number=phone).exists():
        User.objects.create_user(phone_number=phone, password='testpassword')
        print(f"Created user {phone}")
    
    # 2. Test with local format
    data = {
        "phone_number": "08012345678",
        "password": "testpassword"
    }
    
    print(f"Validating data: {data}")
    serializer = CustomTokenObtainPairSerializer(data=data)
    
    if serializer.is_valid():
        print("Validation SUCCESS!")
        print(f"Validated Data: {serializer.validated_data.keys()}")
    else:
        print("Validation FAILED!")
        print(f"Errors: {serializer.errors}")

except Exception as e:
    import traceback
    traceback.print_exc()
