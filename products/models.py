from decimal import Decimal
from django.db import models


class AccountProduct(models.Model):
    class ProductType(models.TextChoices):
        SAVINGS = 'SAVINGS', 'Savings'
        CURRENT = 'CURRENT', 'Current'

    product_code = models.CharField(max_length=20, unique=True)
    product_name = models.CharField(max_length=100)
    product_type = models.CharField(
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.SAVINGS,
    )
    description = models.TextField(blank=True, null=True)
    minimum_balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    currency = models.CharField(max_length=10, default='BDT')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Account Product"
        verbose_name_plural = "Account Products"
        ordering = ['product_code']

    def __str__(self):
        return f"{self.product_code} - {self.product_name}"
