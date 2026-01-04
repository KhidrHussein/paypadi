import os
import django
import sys

print("Setting up Django...")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'paypadi.settings')
django.setup()
print("Django setup complete.")

print("Importing phonenumbers...")
try:
    import phonenumbers
    print(f"Phonenumbers imported: {phonenumbers.__version__}")
except ImportError as e:
    print(f"Failed to import phonenumbers: {e}")
    sys.exit(1)

print("Importing User model...")
try:
    from django.contrib.auth import get_user_model
    User = get_user_model()
    print(f"User model: {User}")
except Exception as e:
    print(f"Failed to get User model: {e}")
    sys.exit(1)

print("All checks passed.")
