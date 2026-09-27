from django.contrib import admin
from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('branch_code', 'branch_name', 'district', 'routing_number', 'is_active')
    search_fields = ('branch_code', 'branch_name', 'routing_number')
    list_filter = ('district', 'is_active')
    readonly_fields = ('created_at', 'updated_at')
