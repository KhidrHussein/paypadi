from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _
from .models import User, UserProfile, DriverProfile, OTP


class UserAdmin(BaseUserAdmin):
    # The forms to add and change user instances
    form = UserChangeForm
    add_form = UserCreationForm
    
    # The fields to be used in displaying the User model.
    list_display = ('phone_number', 'email', 'first_name', 'last_name', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'email')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'email', 'password1', 'password2'),
        }),
    )
    search_fields = ('phone_number', 'first_name', 'last_name', 'email')
    ordering = ('phone_number',)
    filter_horizontal = ('groups', 'user_permissions',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'date_of_birth', 'is_email_verified')
    search_fields = ('user__phone_number', 'user__email', 'user__first_name', 'user__last_name')


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'vehicle_make', 'vehicle_model', 'is_approved')
    list_filter = ('is_approved', 'is_available')
    search_fields = ('user__phone_number', 'user__email', 'vehicle_make', 'vehicle_model')


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'purpose', 'is_used', 'created_at', 'expires_at')
    list_filter = ('purpose', 'is_used')
    search_fields = ('phone_number',)
    readonly_fields = ('code', 'created_at', 'expires_at')


# Register the User model with the custom admin class
admin.site.register(User, UserAdmin)
