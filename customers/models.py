from datetime import date
from django.db import models, connection
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from branches.models import Branch


def generate_next_cif_number():
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute("SELECT nextval('customer_cif_seq')")
            seq_val = cursor.fetchone()[0]
        else:
            # Fallback for non-PostgreSQL (e.g. SQLite unit tests)
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM customers_customer")
            row = cursor.fetchone()
            seq_val = row[0] if row and row[0] else 1
            last_customer = Customer.objects.order_by('-id').first()
            if last_customer and last_customer.cif_number and last_customer.cif_number.startswith("CIF"):
                try:
                    num = int(last_customer.cif_number[3:])
                    if seq_val <= num:
                        seq_val = num + 1
                except ValueError:
                    pass
    return f"CIF{seq_val:08d}"


class Customer(models.Model):
    class CustomerType(models.TextChoices):
        INDIVIDUAL = 'INDIVIDUAL', 'Individual'
        ORGANIZATION = 'ORGANIZATION', 'Organization'

    class Gender(models.TextChoices):
        MALE = 'MALE', 'Male'
        FEMALE = 'FEMALE', 'Female'
        OTHER = 'OTHER', 'Other'

    class KYCStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        VERIFIED = 'VERIFIED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected'

    class RiskLevel(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        BLOCKED = 'BLOCKED', 'Blocked'

    # Identity
    cif_number = models.CharField(max_length=20, unique=True, editable=False, blank=True)
    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.INDIVIDUAL,
    )
    full_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        blank=True,
        null=True,
    )
    nid_number = models.CharField(max_length=30, unique=True, blank=True, null=True)
    passport_number = models.CharField(max_length=30, unique=True, blank=True, null=True)

    # Contact
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    present_address = models.TextField()
    permanent_address = models.TextField(blank=True, null=True)
    district = models.CharField(max_length=100)

    # KYC
    kyc_status = models.CharField(
        max_length=20,
        choices=KYCStatus.choices,
        default=KYCStatus.PENDING,
    )
    risk_level = models.CharField(
        max_length=20,
        choices=RiskLevel.choices,
        default=RiskLevel.LOW,
    )

    # Nominee
    nominee_name = models.CharField(max_length=150, blank=True, null=True)
    nominee_relationship = models.CharField(max_length=50, blank=True, null=True)
    nominee_phone = models.CharField(max_length=20, blank=True, null=True)

    # Banking relationship
    home_branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name='customers')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_customers')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        errors = {}

        # 1. Phone required check
        if not self.phone or not self.phone.strip():
            errors['phone'] = "Phone number cannot be blank."

        # 2. Individual customer identity validation
        if self.customer_type == self.CustomerType.INDIVIDUAL:
            if not self.nid_number and not self.passport_number:
                errors['nid_number'] = "An individual customer must have at least NID or passport information."

        # 3. Date of birth validation
        if self.date_of_birth and self.date_of_birth > date.today():
            errors['date_of_birth'] = "Date of birth cannot be in the future."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.cif_number:
            self.cif_number = generate_next_cif_number()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.cif_number} - {self.full_name}"
