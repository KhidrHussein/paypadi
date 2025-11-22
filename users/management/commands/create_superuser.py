from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a superuser with a phone number'

    def handle(self, *args, **options):
        phone_number = '+2348000000000'  # Default phone number
        email = 'admin@example.com'
        password = 'admin123'
        first_name = 'Admin'
        last_name = 'User'

        if not User.objects.filter(phone_number=phone_number).exists():
            User.objects.create_superuser(
                phone_number=phone_number,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_staff=True,
                is_superuser=True,
                is_active=True,
                verified_phone=True
            )
            self.stdout.write(self.style.SUCCESS('Superuser created successfully!'))
            self.stdout.write(f'Phone: {phone_number}')
            self.stdout.write(f'Password: {password}')
        else:
            self.stdout.write(self.style.WARNING('Superuser already exists!'))
