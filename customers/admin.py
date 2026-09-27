from django.contrib import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        'cif_number',
        'full_name',
        'phone',
        'nid_number',
        'home_branch',
        'kyc_status',
        'risk_level',
        'status',
    )
    search_fields = (
        'cif_number',
        'full_name',
        'phone',
        'nid_number',
        'passport_number',
    )
    list_filter = (
        'home_branch',
        'kyc_status',
        'risk_level',
        'status',
        'customer_type',
    )
    readonly_fields = ('cif_number', 'created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if not change and not hasattr(obj, 'created_by'):
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
