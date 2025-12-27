from django.urls import path, include
from rest_framework.routers import DefaultRouter
from django.views.decorators.csrf import csrf_exempt
from . import views
from .api_views import (
    PaymentInitiationView,
    TransferFundsView,
    VerifyBankAccountView,
    PaymentVerificationView,
    PaymentWebhookView,
    TransactionHistoryView
)
from .views_paystack import paystack_webhook

router = DefaultRouter()
router.register(r'beneficiaries', views.BeneficiaryViewSet, basename='beneficiary')

urlpatterns = [
    # Wallet endpoints
    path('wallet/', views.WalletView.as_view(), name='wallet-detail'),
    
    # Transaction endpoints
    path('transactions/', TransactionHistoryView.as_view(), name='transaction-list'),
    path('transactions/<str:reference>/', views.TransactionDetailView.as_view(), name='transaction-detail'),
    
    # Payment endpoints
    path('payments/initiate/', PaymentInitiationView.as_view(), name='initiate-payment'),
    path('payments/verify/<str:reference>/', PaymentVerificationView.as_view(), name='payment-verify'),
    path('payments/webhook/', PaymentWebhookView.as_view(), name='payment-webhook'),
    path('payments/paystack/webhook/', csrf_exempt(paystack_webhook), name='paystack-webhook'),
    
    # Fund transfer endpoints
    path('transfer/', TransferFundsView.as_view(), name='transfer-funds'),
    path('deposit/', views.DepositFundsView.as_view(), name='deposit-funds'),
    path('withdraw/', views.WithdrawFundsView.as_view(), name='withdraw-funds'),
    
    # Bank account verification
    path('bank/verify/', VerifyBankAccountView.as_view(), name='verify-bank-account'),
    
    # Include router URLs (for beneficiaries)
    path('', include(router.urls)),
]
