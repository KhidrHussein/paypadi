"""
URL configuration for paypadi project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

# Import Swagger configuration
from .swagger_config import schema_view, SWAGGER_SETTINGS

# Import custom admin auth
from users.admin_auth import admin_jwt_login

# JWT Token endpoints
jwt_patterns = [
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('admin-login/', csrf_exempt(admin_jwt_login), name='admin_jwt_login'),
]

urlpatterns = [
    # Admin site
    path('admin/', admin.site.urls),
    
    # API v1
    path('api/v1/auth/', include('users.urls')),  # Authentication and user management
    path('api/v1/wallets/', include('wallets.urls')),  # Wallet and transaction management
    path('api/v1/auth/jwt/', include(jwt_patterns)),
    
    # API Documentation
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
