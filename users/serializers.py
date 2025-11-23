from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from phonenumber_field.serializerfields import PhoneNumberField
from django.contrib.auth import get_user_model
from .models import OTP, UserProfile, DriverProfile

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
        min_length=8
    )
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
            'referred_by', 'role'
        ]
    
    def create(self, validated_data):
        """
        Create and return a new user instance, given the validated data.
        """
        referred_by_code = validated_data.pop('referred_by', None)
        role = validated_data.pop('role', User.UserRole.RIDER)
        
        user = User.objects.create_user(
            phone_number=validated_data['phone_number'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            email=validated_data.get('email', ''),
            role=role
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
        min_length=8,
        style={'input_type': 'password'}
    )


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
