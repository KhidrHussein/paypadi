from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

import phonenumbers

User = get_user_model()

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom token obtain serializer that allows login with phone number and password.
    Also includes additional user data in the token response.
    """
    username_field = 'phone_number'
    
    def validate(self, attrs):
        # Replace the username field with phone_number
        if 'username' in attrs:
            attrs['phone_number'] = attrs.pop('username')
        
        # Normalize phone number
        phone_number = attrs.get('phone_number')
        if phone_number:
            try:
                # Parse the phone number
                parsed_number = phonenumbers.parse(phone_number, "NG")  # Default to NG region
                if phonenumbers.is_valid_number(parsed_number):
                    # Format to E.164 (e.g., +2348012345678)
                    attrs['phone_number'] = phonenumbers.format_number(
                        parsed_number, 
                        phonenumbers.PhoneNumberFormat.E164
                    )
            except phonenumbers.NumberParseException:
                pass  # Use original input if parsing fails

        # Check if the user exists and is active
        try:
            user = User.objects.get(phone_number=attrs['phone_number'])
            if not user.is_active:
                raise serializers.ValidationError(
                    _('Account is not active. Please contact support.'),
                    code='account_inactive'
                )
                
            # Check if the user is a driver and if driver profile is approved
            if hasattr(user, 'driver_profile'):
                if not user.driver_profile.is_approved:
                    raise serializers.ValidationError(
                        _('Your driver account is pending approval. Please wait for admin approval.'),
                        code='driver_pending_approval'
                    )
                
        except User.DoesNotExist:
            raise serializers.ValidationError(
                _('No account found with this phone number.'),
                code='user_not_found'
            )
        
        # Validate credentials
        to_validate = attrs.copy()
        if 'phone_number' in to_validate and 'username' not in to_validate:
             # TokenObtainPairSerializer might expect username, so we map it back or rely on custom backend
             # But here we are calling super().validate(attrs). 
             # super() uses self.username_field which is 'phone_number' (we set it).
             pass
             
        data = super().validate(attrs)
        
        # Add custom claims
        refresh = self.get_token(self.user)
        
        # Add custom claims to the token
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)
        data['user'] = {
            'id': self.user.id,
            'phone_number': self.user.phone_number,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'is_driver': hasattr(self.user, 'driver_profile'),
        }
        
        # Add driver-specific data if user is a driver
        if hasattr(self.user, 'driver_profile'):
            driver = self.user.driver_profile
            data['user'].update({
                'driver_id': str(driver.id),
                'is_approved': driver.is_approved,
                'vehicle_number': driver.vehicle_number,
                'driver_license_number': driver.driver_license_number,
            })
        
        return data


from rest_framework_simplejwt.serializers import TokenRefreshSerializer

class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Custom token refresh serializer that includes user data in the response.
    """
    
    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = self.token_class(attrs["refresh"])
        
        # Add user data to the response
        if hasattr(refresh, 'user'):
            user = refresh.user
            data['user'] = {
                'id': user.id,
                'phone_number': user.phone_number,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'is_driver': hasattr(user, 'driver_profile'),
            }
            
            # Add driver-specific data if user is a driver
            if hasattr(user, 'driver_profile'):
                driver = user.driver_profile
                data['user'].update({
                    'driver_id': str(driver.id),
                    'is_approved': driver.is_approved,
                    'vehicle_number': driver.vehicle_number,
                    'driver_license_number': driver.driver_license_number,
                })
        
        return data
