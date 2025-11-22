from rest_framework_simplejwt.views import (
    TokenObtainPairView as BaseTokenObtainPairView,
    TokenRefreshView as BaseTokenRefreshView,
    TokenVerifyView as BaseTokenVerifyView,
)
from .jwt_serializers import (
    CustomTokenObtainPairSerializer,
    CustomTokenRefreshSerializer
)


class TokenObtainPairView(BaseTokenObtainPairView):
    """
    Custom token obtain view that uses phone number for authentication.
    """
    serializer_class = CustomTokenObtainPairSerializer


class TokenRefreshView(BaseTokenRefreshView):
    """
    Custom token refresh view that includes user data in the response.
    """
    serializer_class = CustomTokenRefreshSerializer


class TokenVerifyView(BaseTokenVerifyView):
    """
    Custom token verify view that includes user data in the response.
    """
    pass
