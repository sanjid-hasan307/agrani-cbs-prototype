from django.contrib import admin
from .models import StaffProfile


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = (
        'employee_id',
        'get_username',
        'get_full_name',
        'branch',
        'get_roles',
        'designation',
        'is_active',
    )
    search_fields = (
        'employee_id',
        'user__username',
        'user__first_name',
        'user__last_name',
    )
    list_filter = ('branch', 'is_active')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Username')
    def get_username(self, obj):
        return obj.user.username

    @admin.display(description='Full Name')
    def get_full_name(self, obj):
        name = obj.user.get_full_name()
        return name if name else obj.user.username

    @admin.display(description='Role/Group')
    def get_roles(self, obj):
        roles = [group.name for group in obj.user.groups.all()]
        return ", ".join(roles) if roles else "-"
