from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from phonenumber_field.serializerfields import PhoneNumberField
from django.contrib.auth import get_user_model
from .models import OTP, UserProfile, DriverProfile, DriverPayoutAccount

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for the User model."""
    phone_number = PhoneNumberField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="A user with this phone number already exists."
            )
        ]
    )
    
    class Meta:
        model = User
        fields = [
            'id', 'phone_number', 'first_name', 'last_name', 'email',
            'is_active', 'verified_phone', 'role', 'date_joined'
        ]
        read_only_fields = ['id', 'is_active', 'verified_phone', 'date_joined', 'role']


class DriverPayoutAccountSerializer(serializers.ModelSerializer):
    """Serializer for driver payout accounts."""
    
    class Meta:
        model = DriverPayoutAccount
        fields = [
            'id', 'account_type', 'account_name', 'account_number',
            'bank_name', 'bank_code', 'is_primary', 'is_verified',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'is_verified', 'created_at', 'updated_at']
    
    def validate(self, data):
        # If it's a bank account, bank_name and bank_code are required
        if data.get('account_type') == 'bank_account':
            if not data.get('bank_name') or not data.get('bank_code'):
                raise serializers.ValidationError({
                    'bank_name': 'Bank name is required for bank accounts',
                    'bank_code': 'Bank code is required for bank accounts'
                })
        return data


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""
    phone_number = PhoneNumberField(
        required=True,
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="A user with this phone number already exists."
            )
        ]
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
        min_length=6,
        max_length=6,
        help_text="Must be a 6-digit number"
    )
    
    # Driver-specific fields
    vehicle_make = serializers.CharField(
        write_only=True, 
        required=False,
        allow_blank=True,
        allow_null=True
    )
    vehicle_model = serializers.CharField(
        write_only=True, 
        required=False,
        allow_blank=True,
        allow_null=True
    )
    license_plate = serializers.CharField(
        write_only=True, 
        required=False,
        allow_blank=True,
        allow_null=True
    )
    driver_license_number = serializers.CharField(
        write_only=True, 
        required=False,
        allow_blank=True,
        allow_null=True
    )
    
    def validate_password(self, value):
        """Validate that the password is a 6-digit number."""
        if not value.isdigit():
            raise serializers.ValidationError("Password must be a 6-digit number")
        return value
    referred_by = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True
    )
    role = serializers.ChoiceField(
        choices=User.UserRole.choices,
        default=User.UserRole.RIDER,
        write_only=True,
        required=False
    )
    
    class Meta:
        model = User
        fields = [
            'phone_number', 'password', 'first_name', 'last_name', 'email',
            'referred_by', 'role', 'vehicle_make', 'vehicle_model', 
            'license_plate', 'driver_license_number'
        ]
    
    def create(self, validated_data):
        """
        Create and return a new user instance, given the validated data.
        """
        # Extract driver-specific data
        driver_data = {
            'vehicle_make': validated_data.pop('vehicle_make', None),
            'vehicle_model': validated_data.pop('vehicle_model', None),
            'license_plate': validated_data.pop('license_plate', None),
            'driver_license_number': validated_data.pop('driver_license_number', None)
        }
        
        referred_by_code = validated_data.pop('referred_by', None)
        role = validated_data.get('role', User.UserRole.RIDER)
        
        user = User.objects.create_user(
            phone_number=validated_data['phone_number'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            email=validated_data.get('email') or None,
            role=role
        )
        
        # If user is a driver, create driver profile with provided data
        if role == User.UserRole.DRIVER:
            DriverProfile.objects.create(
                user=user,
                **{k: v for k, v in driver_data.items() if v is not None}
            )
        
        # Handle referral if provided
        if referred_by_code:
            try:
                referrer = User.objects.get(referral_code=referred_by_code)
                user.referred_by = referrer
                user.save(update_fields=['referred_by'])
            except User.DoesNotExist:
                pass
        
        return user


class OTPSerializer(serializers.ModelSerializer):
    """Serializer for OTP model."""
    class Meta:
        model = OTP
        fields = ['phone_number', 'code', 'purpose', 'created_at', 'expires_at']
        read_only_fields = ['created_at', 'expires_at']
        extra_kwargs = {
            'code': {'write_only': True},
            'purpose': {'write_only': True}
        }


class OTPRequestSerializer(serializers.Serializer):
    """Serializer for OTP request."""
    phone_number = PhoneNumberField(required=True)
    purpose = serializers.ChoiceField(
        choices=OTP.OTPPurpose.choices,
        required=True
    )


class OTPVerifySerializer(serializers.Serializer):
    """Serializer for OTP verification."""
    phone_number = PhoneNumberField(required=True)
    code = serializers.CharField(required=True, max_length=6, min_length=6)
    purpose = serializers.ChoiceField(
        choices=OTP.OTPPurpose.choices,
        required=True
    )


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile."""
    class Meta:
        model = UserProfile
        fields = [
            'id', 'date_of_birth', 'address', 'city', 'state', 'country',
            'profile_picture', 'id_document', 'id_document_type', 
            'id_document_number', 'is_email_verified', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class DriverProfileSerializer(serializers.ModelSerializer):
    """Serializer for driver profile."""
    class Meta:
        model = DriverProfile
        fields = [
            'id', 'vehicle_make', 'vehicle_model', 'vehicle_year',
            'driver_license_number', 'driver_license_expiry', 'license_plate',
            'is_approved', 'is_available', 'current_location_lat', 
            'current_location_lng', 'rating', 'total_rides', 'created_at',
            'updated_at'
        ]
        read_only_fields = [
            'id', 'is_approved', 'approved_at', 'rejection_reason',
            'created_at', 'updated_at'
        ]


class UserDetailSerializer(serializers.ModelSerializer):
    """Detailed user serializer with profile information."""
    profile = UserProfileSerializer(read_only=True)
    driver_profile = DriverProfileSerializer(read_only=True)
    is_driver = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'phone_number', 'first_name', 'last_name', 'email', 'role',
            'is_active', 'verified_phone', 'is_driver', 'date_joined',
            'last_login', 'profile', 'driver_profile', 'kyc_status'
        ]
        read_only_fields = fields
    
    def get_is_driver(self, obj):
        return obj.role == User.UserRole.DRIVER


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change endpoint."""
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True,
        min_length=6,
        max_length=6,
        style={'input_type': 'password'},
        help_text="Must be a 6-digit number"
    )
    
    def validate_new_password(self, value):
        """Validate that the new password is a 6-digit number."""
        if not value.isdigit():
            raise serializers.ValidationError("Password must be a 6-digit number")
        return value


class SetTransactionPinSerializer(serializers.Serializer):
    """Serializer for setting/updating transaction PIN."""
    current_pin = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Required when changing an existing PIN"
    )
    new_pin = serializers.CharField(
        required=True,
        min_length=4,
        max_length=6,
        write_only=True,
        help_text="4-6 digit PIN"
    )
    confirm_pin = serializers.CharField(
        required=True,
        min_length=4,
        max_length=6,
        write_only=True,
        help_text="Must match new_pin"
    )
    
    def validate(self, attrs):
        if attrs['new_pin'] != attrs['confirm_pin']:
            raise serializers.ValidationError({"confirm_pin": "PINs do not match"})
        return attrs
