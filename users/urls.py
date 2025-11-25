from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .api_views.auth_views import UserLoginView

router = DefaultRouter()
router.register(r'driver/payout-accounts', views.DriverPayoutAccountViewSet, basename='payout-account')

urlpatterns = [
    # User registration and authentication
    path('register/', views.UserRegistrationView.as_view(), name='user-register'),
    path('login/', UserLoginView.as_view(), name='user-login'),
    
    # OTP verification
    path('otp/request/', views.OTPRequestView.as_view(), name='otp-request'),
    path('otp/verify/', views.OTPVerifyView.as_view(), name='otp-verify'),
    
    # User profile - using UserProfileView for both retrieve and update
    path('profile/', views.UserProfileView.as_view(), name='user-profile'),
    
    # Password management
    path('password/change/', views.ChangePasswordView.as_view(), name='change-password'),
    
    # Transaction PIN
    path('pin/set/', views.SetTransactionPinView.as_view(), name='set-transaction-pin'),
    
    # Driver profile - only include available views
    path('driver/profile/', views.DriverProfileView.as_view(), name='driver-profile'),
    
    # Current user info
    path('me/', views.CurrentUserView.as_view(), name='current-user'),
    
    # Include router URLs
    path('', include(router.urls)),
]

# Include router URLs if any
urlpatterns += router.urls
