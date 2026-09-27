from decimal import Decimal
from django.db import models, connection
from django.core.exceptions import ValidationError
from customers.models import Customer
from products.models import AccountProduct
from branches.models import Branch


def generate_next_account_number():
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute("SELECT nextval('account_number_seq')")
            seq_val = cursor.fetchone()[0]
        else:
            # Fallback for SQLite (unit tests)
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM accounts_account")
            row = cursor.fetchone()
            seq_val = row[0] if row and row[0] else 1
            last_account = Account.objects.order_by('-id').first()
            if last_account and last_account.account_number and last_account.account_number.startswith("ACC"):
                try:
                    num = int(last_account.account_number[3:])
                    if seq_val <= num:
                        seq_val = num + 1
                except ValueError:
                    pass
    return f"ACC{seq_val:08d}"


class Account(models.Model):
    class AccountStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        DORMANT = 'DORMANT', 'Dormant'
        FROZEN = 'FROZEN', 'Frozen'
        CLOSED = 'CLOSED', 'Closed'

    # Identity
    account_number = models.CharField(max_length=20, unique=True, editable=False, blank=True)

    # Relationships
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='accounts')
    product = models.ForeignKey(AccountProduct, on_delete=models.PROTECT, related_name='accounts')
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='accounts')

    # Financial
    currency = models.CharField(max_length=10, default='BDT')
    available_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    ledger_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))

    # Status
    account_status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.ACTIVE,
    )

    # Dates
    opening_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
        ordering = ['account_number']

    def clean(self):
        super().clean()
        errors = {}

        # Customer must be active
        if self.customer_id and not self.customer.status == Customer.Status.ACTIVE:
            errors['customer'] = "Account cannot be opened for an inactive or blocked customer."

        # Product must be active
        if self.product_id and not self.product.is_active:
            errors['product'] = "The selected account product is not active."

        # Branch must be active
        if self.branch_id and not self.branch.is_active:
            errors['branch'] = "The selected branch is not active."

        # Balances cannot be negative
        if self.available_balance is not None and self.available_balance < Decimal('0.00'):
            errors['available_balance'] = "Available balance cannot be negative."
        if self.ledger_balance is not None and self.ledger_balance < Decimal('0.00'):
            errors['ledger_balance'] = "Ledger balance cannot be negative."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Set currency from product on first save
        if not self.pk and self.product_id and not self.currency:
            self.currency = self.product.currency
        # Generate account number before validation
        if not self.account_number:
            self.account_number = generate_next_account_number()
        # Set currency from product if not explicitly set
        if not self.currency and self.product_id:
            self.currency = self.product.currency
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.account_number} ({self.customer})"
