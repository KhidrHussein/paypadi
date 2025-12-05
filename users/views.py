import logging
from rest_framework import status, permissions, generics, viewsets, serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from drf_yasg.utils import swagger_auto_schema

import requests
from django.conf import settings
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import User, OTP, UserProfile, DriverProfile, DriverPayoutAccount
from .serializers import (
    UserSerializer, UserRegistrationSerializer, OTPSerializer,
    OTPRequestSerializer, OTPVerifySerializer, UserProfileSerializer,
    DriverProfileSerializer, UserDetailSerializer, ChangePasswordSerializer,
    SetTransactionPinSerializer, DriverPayoutAccountSerializer
)
from core.models import AuditLog


# Response serializers for Swagger documentation
class OTPRequestResponseSerializer(serializers.Serializer):
    """Serializer for OTP request response."""
    detail = serializers.CharField(help_text="Response message")
    expires_in = serializers.IntegerField(help_text="OTP expiration time in seconds")


class OTPVerifyResponseSerializer(serializers.Serializer):
    """Serializer for OTP verification response."""
    detail = serializers.CharField(help_text="Verification result message")


class LoginResponseSerializer(serializers.Serializer):
    """Serializer for login response."""
    refresh = serializers.CharField(help_text="JWT refresh token")
    access = serializers.CharField(help_text="JWT access token")
    user = UserSerializer(help_text="Authenticated user details")


class LogoutRequestSerializer(serializers.Serializer):
    """Serializer for logout request."""
    refresh = serializers.CharField(required=True, help_text="Refresh token to invalidate")


class LogoutResponseSerializer(serializers.Serializer):
    """Serializer for logout response."""
    detail = serializers.CharField(help_text="Logout status message")


class UserRegistrationResponseSerializer(serializers.Serializer):
    """Serializer for user registration response."""
    refresh = serializers.CharField(help_text="JWT refresh token")
    access = serializers.CharField(help_text="JWT access token")
    user = UserSerializer(help_text="Registered user details")

logger = logging.getLogger(__name__)


class OTPRequestView(APIView):
    """
    Request an OTP for phone verification.
    
    This endpoint sends a one-time password (OTP) to the provided phone number
    for verification purposes.
    
    ## Request Body
    - `phone_number`: User's phone number in international format (e.g., +1234567890) (required)
    - `purpose`: Purpose of the OTP (e.g., 'registration', 'password_reset') (required)
    
    ## Response
    - `detail`: Success message
    - `expires_in`: Time in seconds until the OTP expires
    
    ### Example Request
    ```json
    {
        "phone_number": "+1234567890",
        "purpose": "registration"
    }
    ```
    
    ### Example Response
    ```json
    {
        "detail": "OTP sent successfully",
        "expires_in": 300
    }
    """
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Request an OTP for phone verification",
        request_body=OTPRequestSerializer,
        responses={
            200: OTPRequestResponseSerializer(),
            400: "Invalid input data",
            429: "Too many requests"
        }
    )
    def post(self, request):
        """Handle OTP request and send OTP to the provided phone number."""
        serializer = OTPRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        phone_number = serializer.validated_data['phone_number']
        purpose = serializer.validated_data['purpose']
        
        # Check rate limiting
        cache_key = f'otp_rate_limit:{phone_number}'
        if cache.get(cache_key):
            return Response(
                {"detail": "Please wait before requesting another OTP"},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        # Create and send OTP
        from core.models import OTPManager
        otp = OTPManager.create_otp(phone_number, purpose)
        
        # Set rate limit (1 OTP per 60 seconds)
        cache.set(cache_key, True, 60)
        
        # Log the OTP request (in production, don't log the actual OTP)
        AuditLog.log_action(
            action='otp_requested',
            user=None,
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            data={'phone_number': str(phone_number), 'purpose': purpose}
        )
        
        return Response({
            "detail": "OTP sent successfully",
            "expires_in": 300,  # 5 minutes
            "otp": otp.code  # Include OTP in response for development
        })
    
    def get_client_ip(self, request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class OTPVerifyView(APIView):
    """
    Verify an OTP code.
    
    This endpoint verifies the one-time password (OTP) sent to the user's phone number.
    
    ## Request Body
    - `phone_number`: User's phone number in international format (e.g., +1234567890) (required)
    - `code`: The OTP code to verify (6 digits) (required)
    - `purpose`: Purpose of the OTP (must match the purpose when requested) (required)
    
    ## Response
    - `detail`: Verification result message
    
    ### Example Request
    ```json
    {
        "phone_number": "+1234567890",
        "code": "123456",
        "purpose": "registration"
    }
    ```
    
    ### Example Response
    ```json
    {
        "detail": "OTP verified successfully"
    }
    """
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Verify an OTP code",
        request_body=OTPVerifySerializer,
        responses={
            200: OTPVerifyResponseSerializer(),
            400: "Invalid OTP or expired",
            404: "OTP not found"
        }
    )
    def post(self, request):
        """Verify the provided OTP code for the given phone number and purpose."""
        serializer = OTPVerifySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        phone_number = serializer.validated_data['phone_number']
        code = serializer.validated_data['code']
        purpose = serializer.validated_data['purpose']
        
        # Verify OTP
        from core.models import OTPManager
        is_valid, error = OTPManager.verify_otp(phone_number, code, purpose)
        
        if not is_valid:
            AuditLog.log_action(
                action='otp_verification_failed',
                user=None,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                data={
                    'phone_number': str(phone_number),
                    'purpose': purpose,
                    'error': error
                }
            )
            return Response(
                {"detail": error or "Invalid OTP"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Mark OTP as used
            otp = OTP.objects.get(phone_number=phone_number, code=code, purpose=purpose)
            otp.is_used = True
            otp.used_at = timezone.now()
            otp.save()
            
            # Set session variables for registration flow
            request.session['phone_verified'] = True
            request.session['verified_phone'] = str(phone_number)
            request.session.set_expiry(300)  # 5 minutes expiry
            request.session.save()  # Explicitly save the session
            
            # Log successful verification
            AuditLog.log_action(
                action='otp_verified',
                user=None,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                data={
                    'phone_number': str(phone_number), 
                    'purpose': purpose,
                    'session_id': request.session.session_key
                }
            )
            
            return Response({
                "detail": "OTP verified successfully",
                "session_id": request.session.session_key  # For debugging
            })
            
        except OTP.DoesNotExist:
            return Response(
                {"detail": "Invalid OTP"},
                status=status.HTTP_400_BAD_REQUEST
            )
        if refresh:
            response_data.update({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            })
        
        return Response(response_data)


class UserRegistrationView(APIView):
    """
    Register a new user account.
    
    This endpoint creates a new user account with the provided information.
    
    ## Request Body
    - `phone_number`: User's phone number in international format (required)
    - `password`: User's password (min 8 characters, required)
    - `first_name`: User's first name (optional)
    - `last_name`: User's last name (optional)
    - `email`: User's email address (optional)
    - `referred_by`: Referral code (optional)
    
    ## Response
    - `detail`: Success message
    - `user`: Registered user details
    - `refresh`: JWT refresh token
    - `access`: JWT access token
    
    ### Example Request
    ```json
    {
        "phone_number": "+1234567890",
        "password": "securepassword123",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "role": "rider"  # or "driver"
    }
    ```
    
    ### Example Response
    ```json
    {
        "detail": "User registered successfully",
        "user": {
            "id": 1,
            "phone_number": "+1234567890",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "is_active": true,
            "is_verified": true,
            "is_driver": false,
            "date_joined": "2023-01-01T00:00:00Z"
        },
        "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    """
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Register a new user account",
        request_body=UserRegistrationSerializer,
        responses={
            201: UserRegistrationResponseSerializer(),
            400: "Invalid input data or phone not verified",
            500: "Internal server error"
        }
    )
    def post(self, request):
        """Handle user registration with phone verification."""
        # Check if phone is verified
        if not request.session.get('phone_verified'):
            return Response(
                {"detail": "Phone number not verified"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the verified phone from session
        phone_number = request.session.get('verified_phone')
        
        # Add phone_number to request data if not provided
        request_data = request.data.copy()
        if 'phone_number' not in request_data:
            request_data['phone_number'] = phone_number
        
        serializer = UserRegistrationSerializer(data=request_data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Create user
                user = serializer.save()
                
                # Mark phone as verified
                user.verified_phone = True
                user.save(update_fields=['verified_phone'])
                
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                
                # Create user profile - Handled by post_save signal
                # UserProfile.objects.create(user=user)
                
                # Log the registration
                AuditLog.log_action(
                    action='user_registered',
                    user=user,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT'),
                    data={
                        'phone_number': str(user.phone_number),
                        'referred_by': str(user.referred_by) if user.referred_by else None
                    }
                )
                
                # Clear the verification session
                if 'phone_verified' in request.session:
                    del request.session['phone_verified']
                if 'verified_phone' in request.session:
                    del request.session['verified_phone']
                
                return Response({
                    "detail": "User registered successfully",
                    "user": UserSerializer(user).data,
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                }, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error during user registration: {str(e)}")
            return Response(
                {"detail": "An error occurred during registration"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LoginRequestSerializer(serializers.Serializer):
    """Serializer for login request."""
    phone_number = serializers.CharField(required=True, help_text="User's phone number")
    password = serializers.CharField(
        required=True, 
        style={'input_type': 'password'},
        help_text="User's password"
    )


class UserLoginView(APIView):
    """
    Authenticate user and return JWT tokens.
    
    This endpoint authenticates a user with their phone number and password,
    and returns JWT tokens for accessing protected endpoints.
    
    ## Request Body
    - `phone_number`: User's registered phone number (required)
    - `password`: User's password (required)
    
    ## Response
    - `user`: Authenticated user details
    - `refresh`: JWT refresh token
    - `access`: JWT access token
    
    ### Example Request
    ```json
    {
        "phone_number": "+1234567890",
        "password": "securepassword123"
    }
    ```
    
    ### Example Response
    ```json
    {
        "user": {
            "id": 1,
            "phone_number": "+1234567890",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "is_active": true,
            "is_verified": true,
            "is_driver": false,
            "date_joined": "2023-01-01T00:00:00Z"
        },
        "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    """
    permission_classes = [permissions.AllowAny]
    
    @swagger_auto_schema(
        operation_description="Authenticate user and get JWT tokens",
        request_body=LoginRequestSerializer,
        responses={
            200: LoginResponseSerializer(),
            400: "Missing required fields",
            401: "Invalid credentials",
            403: "Account is disabled"
        }
    )
    def post(self, request):
        """Handle user authentication and return JWT tokens."""
        phone_number = request.data.get('phone_number')
        password = request.data.get('password')
        
        if not phone_number or not password:
            return Response(
                {"detail": "Phone number and password are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = authenticate(request, phone_number=phone_number, password=password)
        
        if user is None:
            AuditLog.log_action(
                action='login_failed',
                user=None,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT'),
                data={'phone_number': phone_number}
            )
            return Response(
                {"detail": "Invalid phone number or password"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if not user.is_active:
            return Response(
                {"detail": "Account is disabled"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Log the user in
        login(request, user)
        
        # Generate tokens
        refresh = RefreshToken.for_user(user)
        
        # Update last login
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        # Log the successful login
        AuditLog.log_action(
            action='login_success',
            user=user,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        return Response({
            "user": UserSerializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        })


class UserLogoutView(APIView):
    """
    Log out the current user.
    
    This endpoint logs out the current user by invalidating the provided refresh token
    and clearing the user's session.
    
    ## Request Body
    - `refresh`: The refresh token to invalidate (optional but recommended)
    
    ## Response
    - `detail`: Logout status message
    
    ### Example Request
    ```json
    {
        "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    ```
    
    ### Example Response
    ```json
    {
        "detail": "Successfully logged out"
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Log out the current user",
        request_body=LogoutRequestSerializer,
        responses={
            200: LogoutResponseSerializer(),
            400: "Invalid refresh token",
            401: "Authentication credentials were not provided"
        }
    )
    def post(self, request):
        """Handle user logout and token invalidation."""
        # Invalidate the refresh token
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
                
                # Log the token blacklist
                AuditLog.log_action(
                    action='token_blacklisted',
                    user=request.user,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT'),
                    data={'token_type': 'refresh'}
                )
        except Exception as e:
            logger.error(f"Error blacklisting token: {e}")
        
        # Log the logout
        AuditLog.log_action(
            action='user_logout',
            user=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT')
        )
        
        # Log the user out
        logout(request)
        
        return Response({"detail": "Successfully logged out"})


class UserProfileView(generics.RetrieveUpdateAPIView):
    """View to retrieve and update user profile."""
    serializer_class = UserDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Use different serializers for user and profile data
        user_serializer = UserSerializer(
            instance,
            data=request.data,
            partial=partial
        )
        
        profile_serializer = UserProfileSerializer(
            instance.profile,
            data=request.data,
            partial=partial
        )
        
        if user_serializer.is_valid() and profile_serializer.is_valid():
            with transaction.atomic():
                self.perform_update(user_serializer)
                self.perform_update(profile_serializer)
                
                # Log the profile update
                AuditLog.log_action(
                    action='profile_updated',
                    user=instance,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT'),
                    data={
                        'updated_fields': list(user_serializer.validated_data.keys()) +
                                       list(profile_serializer.validated_data.keys())
                    }
                )
                
                return Response(UserDetailSerializer(instance).data)
        
        errors = {}
        if user_serializer.errors:
            errors.update(user_serializer.errors)
        if profile_serializer.errors:
            errors.update(profile_serializer.errors)
            
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """
    Change user password.
    
    This endpoint allows users to change their password by providing their current password
    and the new password.
    
    ## Request Body
    - `old_password`: Current password (required)
    - `new_password`: New password (min 8 characters, required)
    
    ## Response
    - `detail`: Success message
    
    ### Example Request
    ```json
    {
        "old_password": "currentpassword123",
        "new_password": "newsecurepassword456"
    }
    ```
    
    ### Example Response
    ```json
    {
        "detail": "Password updated successfully"
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Change user password",
        request_body=ChangePasswordSerializer,
        responses={
            200: "{\"detail\": \"Password updated successfully\"}",
            400: "Invalid input data or wrong password"
        }
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {"old_password": ["Wrong password."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Log the password change
        AuditLog.log_action(
            action='password_changed',
            user=user,
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            data={}
        )
        
        return Response({"detail": "Password updated successfully"})
    
    def get_client_ip(self, request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SetTransactionPinView(APIView):
    """
    Set or update transaction PIN.
    
    This endpoint allows users to set a new transaction PIN or update an existing one.
    If the user already has a PIN set, they must provide the current PIN to update it.
    
    ## Request Body
    - `current_pin`: Current PIN (required if updating existing PIN)
    - `new_pin`: New 4-6 digit PIN (required)
    - `confirm_pin`: Must match new_pin (required)
    
    ## Response
    - `detail`: Success message
    
    ### Example Request (Setting new PIN)
    ```json
    {
        "new_pin": "1234",
        "confirm_pin": "1234"
    }
    ```
    
    ### Example Request (Updating existing PIN)
    ```json
    {
        "current_pin": "1234",
        "new_pin": "5678",
        "confirm_pin": "5678"
    }
    ```
    
    ### Example Response
    ```json
    {
        "detail": "Transaction PIN updated successfully"
    }
    """
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Set or update transaction PIN",
        request_body=SetTransactionPinSerializer,
        responses={
            200: "{\"detail\": \"Transaction PIN updated successfully\"}",
            400: "Invalid input data, PINs don't match, or wrong current PIN"
        }
    )
    def post(self, request):
        serializer = SetTransactionPinSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user = request.user
        
        # If user already has a PIN, require current PIN
        if user.transaction_pin and not user.check_transaction_pin(serializer.validated_data.get('current_pin', '')):
            return Response(
                {"current_pin": ["Incorrect current PIN"]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Set new transaction PIN
        user.set_transaction_pin(serializer.validated_data['new_pin'])
        user.save()
        
        # Log the PIN change
        AuditLog.log_action(
            action='transaction_pin_updated',
            user=user,
            ip_address=self.get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            data={}
        )
        
        return Response({"detail": "Transaction PIN updated successfully"})
    
    def get_client_ip(self, request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class DriverProfileView(generics.RetrieveUpdateAPIView):
    """View to retrieve and update driver profile."""
    serializer_class = DriverProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        # Get or create driver profile
        driver_profile, created = DriverProfile.objects.get_or_create(
            user=self.request.user
        )
        return driver_profile
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Only allow updates if not already approved
        if instance.is_approved and not request.user.is_staff:
            return Response(
                {"detail": "Approved profiles can only be modified by administrators"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        # If updating to submit for approval
        if 'submit_for_approval' in request.data and request.data['submit_for_approval']:
            if not all([
                instance.vehicle_make,
                instance.vehicle_model,
                instance.vehicle_year,
                instance.license_number,
                instance.license_expiry_date,
                instance.license_front,
                instance.license_back,
                instance.vehicle_insurance,
                instance.vehicle_registration
            ]):
                return Response(
                    {"detail": "All driver profile fields must be completed before submission"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            instance.submitted_for_approval = True
            instance.save(update_fields=['submitted_for_approval'])
            
            # Log the submission
            AuditLog.log_action(
                action='driver_profile_submitted',
                user=request.user,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT')
            )
            
            return Response({
                "detail": "Driver profile submitted for approval",
                **serializer.data
            })
        
        # Regular update
        self.perform_update(serializer)
        
        # Log the update
        AuditLog.log_action(
            action='driver_profile_updated',
            user=request.user,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT'),
            data={
                'updated_fields': list(serializer.validated_data.keys())
            }
        )
        
        return Response(serializer.data)


class CurrentUserView(APIView):
    """View to get current user information."""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        serializer = UserDetailSerializer(request.user)
        return Response(serializer.data)


class DriverPayoutAccountViewSet(viewsets.ModelViewSet):
    """ViewSet for managing driver payout accounts."""
    serializer_class = DriverPayoutAccountSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def _verify_bank_account(self, account_number, bank_code):
        """Verify bank account details using Paystack API."""
        paystack_secret_key = settings.PAYSTACK_SECRET_KEY
        headers = {
            'Authorization': f'Bearer {paystack_secret_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            # First, resolve the account number to get the account name
            resolve_url = 'https://api.paystack.co/bank/resolve'
            params = {
                'account_number': account_number,
                'bank_code': bank_code
            }
            
            response = requests.get(resolve_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') and data.get('data'):
                return {
                    'account_name': data['data']['account_name'],
                    'bank_code': bank_code,
                    'account_number': account_number
                }
            
            raise ValidationError("Unable to verify bank account details")
            
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('message', str(e))
                except ValueError:
                    error_message = e.response.text or str(e)
            raise ValidationError(f"Bank account verification failed: {error_message}")

    def get_queryset(self):
        # Only return payout accounts for the current user
        return self.request.user.payout_accounts.all()

    def perform_create(self, serializer):
        # Automatically set the driver to the current user
        serializer.save(driver=self.request.user)
        
    def create(self, request, *args, **kwargs):
        # For bank accounts, verify the account details with Paystack
        account_type = request.data.get('account_type')
        bank_code = request.data.get('bank_code')
        account_number = request.data.get('account_number')
        
        if account_type == 'bank_account' and bank_code and account_number:
            try:
                # Verify the bank account
                account_info = self._verify_bank_account(account_number, bank_code)
                
                # Update the request data with the verified account name
                request.data._mutable = True
                request.data['account_name'] = account_info['account_name']
                request.data['is_verified'] = True
                
            except ValidationError as e:
                return Response(
                    {'detail': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def set_primary(self, request, pk=None):
        """Set an account as primary."""
        account = self.get_object()
        
        # Ensure the account belongs to the current user
        if account.driver != request.user:
            raise PermissionDenied("You don't have permission to modify this account.")
        
        # Set the account as primary
        account.is_primary = True
        account.save()
        
        return Response({'status': 'primary account set'})

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        """Verify a payout account (admin only)."""
        if not request.user.is_staff:
            raise PermissionDenied("Only administrators can verify accounts")
        
        account = self.get_object()
        account.is_verified = True
        account.save()
        return Response({'status': 'account verified'})
        
    @action(detail=False, methods=['get'])
    def list_banks(self, request):
        """
        List all supported banks from Paystack.
        This endpoint returns a list of banks that can be used for bank account verification.
        """
        paystack_secret_key = settings.PAYSTACK_SECRET_KEY
        headers = {
            'Authorization': f'Bearer {paystack_secret_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            # Fetch banks from Paystack
            response = requests.get(
                'https://api.paystack.co/bank',
                headers=headers,
                params={'currency': 'NGN'}  # Filter for Nigerian banks
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') and data.get('data'):
                # Return a simplified version of the bank data
                banks = [{
                    'name': bank['name'],
                    'code': bank['code'],
                    'active': bank['active']
                } for bank in data['data']]
                
                return Response({
                    'status': True,
                    'message': 'Banks retrieved successfully',
                    'data': banks
                })
                
            return Response({
                'status': False,
                'message': 'No banks found',
                'data': []
            }, status=status.HTTP_404_NOT_FOUND)
            
        except requests.exceptions.RequestException as e:
            error_message = str(e)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_message = error_data.get('message', str(e))
                except ValueError:
                    error_message = e.response.text or str(e)
            
            return Response({
                'status': False,
                'message': f'Failed to fetch banks: {error_message}',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)
