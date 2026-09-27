from decimal import Decimal
from django.db import migrations

INITIAL_PRODUCTS = [
    {
        'product_code': 'SAV',
        'product_name': 'Savings Account',
        'product_type': 'SAVINGS',
        'minimum_balance': Decimal('0.00'),
        'currency': 'BDT',
        'is_active': True,
    },
    {
        'product_code': 'CUR',
        'product_name': 'Current Account',
        'product_type': 'CURRENT',
        'minimum_balance': Decimal('0.00'),
        'currency': 'BDT',
        'is_active': True,
    },
]


def create_initial_products(apps, schema_editor):
    AccountProduct = apps.get_model('products', 'AccountProduct')
    for product_data in INITIAL_PRODUCTS:
        AccountProduct.objects.get_or_create(
            product_code=product_data['product_code'],
            defaults=product_data,
        )


def remove_initial_products(apps, schema_editor):
    AccountProduct = apps.get_model('products', 'AccountProduct')
    codes = [p['product_code'] for p in INITIAL_PRODUCTS]
    AccountProduct.objects.filter(product_code__in=codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_initial_products, reverse_code=remove_initial_products),
    ]
