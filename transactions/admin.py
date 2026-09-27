from django.contrib import admin
from .models import Transaction, TransactionEntry


class TransactionEntryInline(admin.TabularInline):
    model = TransactionEntry
    extra = 0
    readonly_fields = ('entry_type', 'account', 'amount')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_id',
        'transaction_type',
        'account',
        'amount',
        'status',
        'authorization_status',
        'created_by',
        'approved_by',
        'created_at',
    )
    search_fields = ('transaction_id', 'account__account_number')
    list_filter = ('transaction_type', 'status', 'authorization_status')
    readonly_fields = ('transaction_id', 'approved_by', 'approved_at', 'created_at', 'updated_at')
    inlines = [TransactionEntryInline]


@admin.register(TransactionEntry)
class TransactionEntryAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'account', 'entry_type', 'amount')
    list_filter = ('entry_type',)
    readonly_fields = ('transaction', 'account', 'entry_type', 'amount')
