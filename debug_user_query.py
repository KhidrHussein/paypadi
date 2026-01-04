import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'paypadi.settings')
django.setup()

from users.models import User
from rest_framework import serializers

try:
    # 1. Create user
    phone = '+2348012345678'
    if User.objects.filter(phone_number=phone).exists():
        print(f"User {phone} already exists, deleting...")
        User.objects.filter(phone_number=phone).delete()
        
    print(f"Creating user with phone: {phone}")
    user = User.objects.create_user(phone_number=phone, password='testpassword')
    print(f"User created: {user} (ID: {user.id})")
    
    # 2. Query user
    print(f"Querying user with string: '{phone}'")
    try:
        u = User.objects.get(phone_number=phone)
        print(f"Found user: {u}")
    except User.DoesNotExist:
        print("ERROR: User not found with string query!")
        
    # 3. Simulate Serializer behavior
    attrs = {'phone_number': phone}
    print(f"Simulating serializer check with attrs: {attrs}")
    try:
        user_check = User.objects.get(phone_number=attrs['phone_number'])
        print(f"Serializer check success: {user_check}")
    except User.DoesNotExist:
        print("ERROR: Serializer check failed!")

    # 4. Test Local Format
    local_phone = '08012345678'
    print(f"Querying with local format: '{local_phone}'")
    try:
        u_local = User.objects.get(phone_number=local_phone)
        print(f"Found user with local format: {u_local}")
    except User.DoesNotExist:
        print("ERROR: User not found with local format!")

    # 5. Check actual DB value
    u = User.objects.get(id=user.id)
    print(f"DB Value for phone_number: {u.phone_number} (Type: {type(u.phone_number)})")

except Exception as e:
    import traceback
    traceback.print_exc()
