from django.contrib import admin
from .models import Account


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        'account_number',
        'customer',
        'product',
        'branch',
        'available_balance',
        'account_status',
    )
    search_fields = (
        'account_number',
        'customer__full_name',
        'customer__cif_number',
    )
    list_filter = ('product', 'branch', 'account_status')
    readonly_fields = ('account_number', 'opening_date', 'created_at', 'updated_at')
