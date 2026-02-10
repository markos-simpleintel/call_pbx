from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Call
from .forms import CustomUserCreationForm, CustomUserChangeForm

class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User
    list_display = ['phone_number', 'is_staff', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('phone_number',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('phone_number',)}),
    )
    # Search by phone number
    search_fields = ['phone_number']
    ordering = ['phone_number']

admin.site.register(User, CustomUserAdmin)

@admin.register(Call)
class CallAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'caller_id', 'user', 'created_at', 'wav_size')
    search_fields = ('session_id', 'caller_id')
    list_filter = ('created_at',)
    ordering = ('-created_at',)
