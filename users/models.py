import uuid
import random
import string
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.core.validators import MinLengthValidator, RegexValidator
from phonenumber_field.modelfields import PhoneNumberField


class UserManager(BaseUserManager):
    """Custom user model manager where email is the unique identifier"""
    
    def create_user(self, phone_number, password=None, **extra_fields):
        """Create and save a user with the given phone number and password."""
        if not phone_number:
            raise ValueError('The Phone Number must be set')
        
        # Set default role to RIDER if not provided
        if 'role' not in extra_fields:
            extra_fields['role'] = self.model.UserRole.RIDER
            
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, phone_number, password=None, **extra_fields):
        """Create and save a SuperUser with the given phone number and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(phone_number, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model that uses phone number as the unique identifier"""
    
    class UserRole(models.TextChoices):
        RIDER = 'rider', 'Rider'
        DRIVER = 'driver', 'Driver'
        ADMIN = 'admin', 'Admin'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = PhoneNumberField(unique=True, db_index=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    role = models.CharField(
        max_length=10, 
        choices=UserRole.choices, 
        default=UserRole.RIDER
    )
    referral_code = models.CharField(
        max_length=8, 
        unique=True, 
        null=True, 
        blank=True,
        help_text="User's unique referral code"
    )
    referred_by = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='referrals'
    )
    transaction_pin_hash = models.CharField(max_length=128, null=True, blank=True)
    kyc_status = models.CharField(
        max_length=10, 
        choices=[
            ('none', 'None'),
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected')
        ],
        default='none'
    )
    verified_phone = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)
    
    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    
    objects = UserManager()
    
    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
    
    def __str__(self):
        return f"{self.phone_number} ({self.get_full_name()})"
    
    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        return f"{self.first_name} {self.last_name}".strip()
    
    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name
    
    def generate_referral_code(self):
        """Generate a unique referral code for the user."""
        if not self.referral_code:
            length = 8
            while True:
                # Generate a random string of uppercase letters and digits
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
                if not User.objects.filter(referral_code=code).exists():
                    self.referral_code = code
                    break
    
    def set_transaction_pin(self, raw_pin):
        """Set the transaction pin for the user."""
        from django.contrib.auth.hashers import make_password
        self.transaction_pin_hash = make_password(raw_pin, salt=None, hasher='pbkdf2_sha256')
        self.save(update_fields=['transaction_pin_hash'])
    
    def check_transaction_pin(self, raw_pin):
        """Check if the provided pin is correct."""
        from django.contrib.auth.hashers import check_password
        return check_password(raw_pin, self.transaction_pin_hash)
    
    def save(self, *args, **kwargs):
        """Override save to generate referral code if not set."""
        if not self.referral_code:
            self.generate_referral_code()
        super().save(*args, **kwargs)


class OTP(models.Model):
    """Model to store OTPs for phone verification and other purposes."""
    
    class OTPPurpose(models.TextChoices):
        LOGIN = 'login', 'Login'
        RESET_PASSWORD = 'reset_password', 'Reset Password'
        TRANSFER_CONFIRM = 'transfer_confirm', 'Transfer Confirmation'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = PhoneNumberField(db_index=True)
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=OTPPurpose.choices)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = 'OTP'
        verbose_name_plural = 'OTPs'
        indexes = [
            models.Index(fields=['phone_number', 'purpose'], name='otp_phone_purpose_idx')
        ]
    
    def __str__(self):
        return f"{self.phone_number} - {self.code} ({self.purpose})"
    
    def is_expired(self):
        """Check if the OTP has expired."""
        return timezone.now() > self.expires_at
    
    def increment_attempts(self):
        """Increment the number of attempts."""
        self.attempts += 1
        self.save(update_fields=['attempts'])
    
    def mark_as_used(self):
        """Mark the OTP as used."""
        self.is_used = True
        self.save(update_fields=['is_used'])


class UserProfile(models.Model):
    """Extended user profile information."""
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE,
        related_name='profile'
    )
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, default='Nigeria')
    profile_picture = models.ImageField(
        upload_to='profile_pics/', 
        null=True, 
        blank=True
    )
    id_document = models.FileField(
        upload_to='id_documents/',
        null=True,
        blank=True,
        help_text='Upload a valid ID document for KYC verification'
    )
    id_document_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        choices=[
            ('national_id', 'National ID'),
            ('passport', 'Passport'),
            ('driver_license', 'Driver\'s License'),
            ('voter_id', 'Voter ID')
        ]
    )
    id_document_number = models.CharField(max_length=50, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.get_full_name()}'s Profile"


class DriverPayoutAccount(models.Model):
    """Model to store driver's payout account information."""
    
    class AccountType(models.TextChoices):
        BANK_ACCOUNT = 'bank_account', 'Bank Account'
        MOBILE_MONEY = 'mobile_money', 'Mobile Money'
    
    driver = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='payout_accounts'
    )
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.BANK_ACCOUNT
    )
    account_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=20, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('driver', 'account_number', 'bank_code')
        ordering = ['-is_primary', '-created_at']

    def __str__(self):
        return f"{self.account_name} - {self.account_number} ({self.get_account_type_display()})"

    def save(self, *args, **kwargs):
        # Ensure only one primary account per driver
        if self.is_primary:
            self.__class__._default_manager.filter(
                driver=self.driver, 
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class DriverProfile(models.Model):
    """Extended profile for drivers."""
    
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE,
        related_name='driver_profile'
    )
    vehicle_make = models.CharField(max_length=100, blank=True, null=True)
    vehicle_model = models.CharField(max_length=100, blank=True, null=True)
    vehicle_year = models.PositiveIntegerField(blank=True, null=True)
    license_plate = models.CharField(max_length=20, unique=True, blank=True, null=True)
    driver_license_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    driver_license_expiry = models.DateField(blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)
    current_location_lat = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        null=True, 
        blank=True
    )
    current_location_lng = models.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        null=True, 
        blank=True
    )
    rating = models.DecimalField(
        max_digits=3, 
        decimal_places=2, 
        default=0.0
    )
    total_rides = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.get_full_name()} - {self.vehicle_make} {self.vehicle_model}"
