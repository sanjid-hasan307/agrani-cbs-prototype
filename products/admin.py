from django.contrib import admin
from .models import AccountProduct


@admin.register(AccountProduct)
class AccountProductAdmin(admin.ModelAdmin):
    list_display = (
        'product_code',
        'product_name',
        'product_type',
        'currency',
        'minimum_balance',
        'is_active',
    )
    search_fields = ('product_code', 'product_name')
    list_filter = ('product_type', 'is_active')
    readonly_fields = ('created_at', 'updated_at')
