from django.contrib import admin
from .models import Wallet, Transaction, Beneficiary

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'reserved_balance', 'currency', 'created_at')
    search_fields = ('user__phone_number', 'user__email', 'user__first_name', 'user__last_name')
    list_filter = ('currency',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'wallet', 'amount', 'transaction_type', 'status', 'created_at')
    search_fields = ('reference', 'wallet__user__phone_number', 'wallet__user__email')
    list_filter = ('transaction_type', 'status', 'created_at')
    readonly_fields = ('reference', 'created_at', 'updated_at')

@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'account_number', 'bank_name', 'beneficiary_type', 'owner', 'created_at')
    search_fields = ('account_name', 'account_number', 'owner__phone_number')
    list_filter = ('beneficiary_type', 'is_verified')
