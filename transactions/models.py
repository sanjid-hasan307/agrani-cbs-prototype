from decimal import Decimal
from django.db import models, connection
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from accounts.models import Account


def generate_next_transaction_id():
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute("SELECT nextval('transaction_id_seq')")
            seq_val = cursor.fetchone()[0]
        else:
            # Fallback for SQLite (unit tests)
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM transactions_transaction")
            row = cursor.fetchone()
            seq_val = row[0] if row and row[0] else 1
            last_txn = Transaction.objects.order_by('-id').first()
            if last_txn and last_txn.transaction_id and last_txn.transaction_id.startswith("TXN"):
                try:
                    num = int(last_txn.transaction_id[3:])
                    if seq_val <= num:
                        seq_val = num + 1
                except ValueError:
                    pass
    return f"TXN{seq_val:08d}"


class Transaction(models.Model):
    class TransactionType(models.TextChoices):
        DEPOSIT = 'DEPOSIT', 'Deposit'
        WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
        TRANSFER = 'TRANSFER', 'Transfer'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        POSTED = 'POSTED', 'Posted'
        REVERSED = 'REVERSED', 'Reversed'

    class AuthorizationStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    transaction_id = models.CharField(max_length=20, unique=True, editable=False, blank=True)
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='transactions')
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    authorization_status = models.CharField(
        max_length=20,
        choices=AuthorizationStatus.choices,
        default=AuthorizationStatus.PENDING,
    )
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='created_transactions'
    )
    authorized_by = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='authorized_transactions',
        blank=True, null=True
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.PROTECT,
        related_name='approved_transactions',
        blank=True, null=True
    )
    approved_at = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount <= Decimal('0.00'):
            errors['amount'] = "Transaction amount must be positive."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = generate_next_transaction_id()
        self.full_clean()
        super().save(*args, **kwargs)

    def validate_entries_balance(self):
        """Validate that total debits equal total credits for this transaction."""
        entries = self.entries.all()
        if not entries.exists():
            raise ValidationError("A transaction must have at least one entry.")
        total_debit = sum(e.amount for e in entries if e.entry_type == TransactionEntry.EntryType.DEBIT)
        total_credit = sum(e.amount for e in entries if e.entry_type == TransactionEntry.EntryType.CREDIT)
        if total_debit != total_credit:
            raise ValidationError(
                f"Total debits ({total_debit}) must equal total credits ({total_credit}) before posting."
            )

    def __str__(self):
        return f"{self.transaction_id} - {self.transaction_type} ({self.status})"


class TransactionEntry(models.Model):
    class EntryType(models.TextChoices):
        DEBIT = 'DEBIT', 'Debit'
        CREDIT = 'CREDIT', 'Credit'

    transaction = models.ForeignKey(Transaction, on_delete=models.PROTECT, related_name='entries')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='entries')
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        verbose_name = "Transaction Entry"
        verbose_name_plural = "Transaction Entries"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal('0.00'):
            raise ValidationError({'amount': "Entry amount must be positive."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.entry_type} {self.amount} on {self.account}"
