import uuid
import json
from datetime import timedelta
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils.functional import cached_property


class TimeStampedModel(models.Model):
    """Abstract base class with self-updating created and updated fields."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditLog(TimeStampedModel):
    """Model to track all important user actions and system events."""
    
    class ActionType(models.TextChoices):
        LOGIN = 'login', 'User Login'
        LOGIN_FAILED = 'login_failed', 'Login Failed'
        LOGOUT = 'logout', 'User Logout'
        PASSWORD_CHANGE = 'password_change', 'Password Changed'
        PROFILE_UPDATE = 'profile_update', 'Profile Updated'
        WALLET_FUND = 'wallet_fund', 'Wallet Funded'
        WALLET_WITHDRAW = 'wallet_withdraw', 'Withdrawal'
        TRANSFER = 'transfer', 'Transfer'
        BENEFICIARY_ADD = 'beneficiary_add', 'Beneficiary Added'
        BENEFICIARY_REMOVE = 'beneficiary_remove', 'Beneficiary Removed'
        KYC_SUBMIT = 'kyc_submit', 'KYC Submitted'
        KYC_APPROVE = 'kyc_approve', 'KYC Approved'
        KYC_REJECT = 'kyc_reject', 'KYC Rejected'
        SYSTEM = 'system', 'System Event'
        OTHER = 'other', 'Other'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=50, choices=ActionType.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default='success')
    error_message = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
    
    def __str__(self):
        return f"{self.get_action_display()} - {self.user or 'System'} - {self.created_at}"
    
    @classmethod
    def log_action(cls, action, user=None, ip_address=None, user_agent=None, data=None, status='success', error_message=None):
        """Helper method to create a new audit log entry."""
        return cls.objects.create(
            user=user,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            data=data or {},
            status=status,
            error_message=error_message
        )


class SystemConfig(TimeStampedModel):
    """Model to store system-wide configuration settings."""
    
    class ConfigType(models.TextChoices):
        STRING = 'string', 'String'
        NUMBER = 'number', 'Number'
        BOOLEAN = 'boolean', 'Boolean'
        JSON = 'json', 'JSON'
    
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    value_type = models.CharField(max_length=10, choices=ConfigType.choices, default=ConfigType.STRING)
    description = models.TextField(blank=True, null=True)
    is_public = models.BooleanField(default=False, help_text='If true, this setting can be read without authentication')
    
    class Meta:
        verbose_name = 'System Configuration'
        verbose_name_plural = 'System Configurations'
    
    def __str__(self):
        return self.key
    
    @cached_property
    def typed_value(self):
        """Return the value cast to the appropriate Python type."""
        if self.value_type == self.ConfigType.NUMBER:
            try:
                return float(self.value) if '.' in self.value else int(self.value)
            except (ValueError, TypeError):
                return 0
        elif self.value_type == self.ConfigType.BOOLEAN:
            return self.value.lower() in ('true', '1', 'yes')
        elif self.value_type == self.ConfigType.JSON:
            try:
                return json.loads(self.value)
            except (json.JSONDecodeError, TypeError):
                return {}
        return self.value
    
    @classmethod
    def get_value(cls, key, default=None):
        """Get a configuration value by key."""
        try:
            return cls.objects.get(key=key).typed_value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def set_value(cls, key, value, value_type=None, description=None, is_public=False):
        """Set a configuration value by key, creating or updating as needed."""
        if value_type is None:
            if isinstance(value, bool):
                value_type = cls.ConfigType.BOOLEAN
            elif isinstance(value, (int, float)):
                value_type = cls.ConfigType.NUMBER
            elif isinstance(value, (dict, list)):
                value_type = cls.ConfigType.JSON
                value = json.dumps(value)
            else:
                value_type = cls.ConfigType.STRING
        
        if value_type == cls.ConfigType.JSON and not isinstance(value, str):
            value = json.dumps(value)
        
        obj, created = cls.objects.update_or_create(
            key=key,
            defaults={
                'value': str(value),
                'value_type': value_type,
                'description': description or f"{key} configuration",
                'is_public': is_public
            }
        )
        return obj


class OTPManager:
    """Manager for handling OTP generation and verification."""
    
    @staticmethod
    def generate_otp(length=6):
        """Generate a random OTP of the specified length."""
        import random
        return ''.join([str(random.randint(0, 9)) for _ in range(length)])
    
    @classmethod
    def create_otp(cls, phone_number, purpose, expiry_minutes=5):
        """Create a new OTP for the given phone number and purpose."""
        from users.models import OTP
        from core.sms import send_sms
        
        # Invalidate any existing OTPs for this phone and purpose
        OTP.objects.filter(
            phone_number=phone_number,
            purpose=purpose,
            is_used=False,
            expires_at__gt=timezone.now()
        ).update(is_used=True)
        
        # Create new OTP
        otp_code = cls.generate_otp()
        otp = OTP.objects.create(
            phone_number=phone_number,
            purpose=purpose,
            code=otp_code,
            expires_at=timezone.now() + timedelta(minutes=expiry_minutes)
        )
        
        # Send OTP via SMS
        message = f"Your Paypadi OTP is: {otp_code}. Valid for {expiry_minutes} minutes."
        send_sms(phone_number, message)
        
        return otp
    
    @classmethod
    def verify_otp(cls, phone_number, code, purpose):
        """Verify an OTP for the given phone number and purpose."""
        from users.models import OTP
        
        try:
            otp = OTP.objects.get(
                phone_number=phone_number,
                code=code,
                purpose=purpose,
                is_used=False,
                expires_at__gt=timezone.now()
            )
            otp.is_used = True
            otp.save(update_fields=['is_used'])
            return True, None
        except OTP.DoesNotExist:
            return False, "Invalid or expired OTP"


class Notification(TimeStampedModel):
    """Model for storing user notifications."""
    
    class NotificationType(models.TextChoices):
        INFO = 'info', 'Information'
        SUCCESS = 'success', 'Success'
        WARNING = 'warning', 'Warning'
        ERROR = 'error', 'Error'
        TRANSACTION = 'transaction', 'Transaction'
        SECURITY = 'security', 'Security Alert'
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.INFO
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    action_url = models.URLField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_notification_type_display()}: {self.title}"
    
    def mark_as_read(self, save=True):
        """Mark the notification as read."""
        self.is_read = True
        self.read_at = timezone.now()
        if save:
            self.save(update_fields=['is_read', 'read_at'])
    
    @classmethod
    def create_notification(
        cls, 
        user, 
        title, 
        message, 
        notification_type=NotificationType.INFO,
        action_url=None,
        metadata=None
    ):
        """Helper method to create a new notification."""
        return cls.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            action_url=action_url,
            metadata=metadata or {}
        )
