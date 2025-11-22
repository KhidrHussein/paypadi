from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db import models

User = get_user_model()

class PhoneOrEmailBackend(ModelBackend):
    """
    Authenticate using either phone number or email.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        
        try:
            # Try to fetch the user by phone number or email
            user = User.objects.get(
                models.Q(phone_number=username) | 
                models.Q(email__iexact=username)
            )
            
            # Check the password
            if user.check_password(password):
                return user
                
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            # Run the default password hasher once to reduce the timing
            # difference between an existing and a non-existing user.
            User().set_password(password)
            
        return None
    
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
