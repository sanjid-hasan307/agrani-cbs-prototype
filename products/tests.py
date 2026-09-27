from decimal import Decimal
from django.test import TestCase
from django.db.utils import IntegrityError
from products.models import AccountProduct


class AccountProductModelTest(TestCase):
    def setUp(self):
        self.product_data = {
            'product_code': 'FD',
            'product_name': 'Fixed Deposit',
            'product_type': AccountProduct.ProductType.SAVINGS,
            'minimum_balance': Decimal('1000.00'),
            'currency': 'BDT',
        }

    def test_product_creation(self):
        product = AccountProduct.objects.create(**self.product_data)
        self.assertEqual(product.product_code, 'FD')
        self.assertEqual(product.product_name, 'Fixed Deposit')
        self.assertEqual(product.product_type, AccountProduct.ProductType.SAVINGS)
        self.assertEqual(product.minimum_balance, Decimal('1000.00'))
        self.assertIsNotNone(product.created_at)
        self.assertIsNotNone(product.updated_at)

    def test_default_currency_is_bdt(self):
        product = AccountProduct.objects.create(
            product_code='TEST',
            product_name='Test Product',
            product_type=AccountProduct.ProductType.CURRENT,
        )
        self.assertEqual(product.currency, 'BDT')

    def test_default_is_active_is_true(self):
        product = AccountProduct.objects.create(
            product_code='TEST2',
            product_name='Test Product 2',
            product_type=AccountProduct.ProductType.SAVINGS,
        )
        self.assertTrue(product.is_active)

    def test_unique_product_code_enforcement(self):
        AccountProduct.objects.create(**self.product_data)
        with self.assertRaises(IntegrityError):
            AccountProduct.objects.create(**self.product_data)

    def test_string_representation(self):
        product = AccountProduct.objects.create(**self.product_data)
        self.assertEqual(str(product), "FD - Fixed Deposit")

    def test_required_product_types_exist(self):
        """Verify the two seeded products from migration exist."""
        self.assertTrue(AccountProduct.objects.filter(product_code='SAV', product_type='SAVINGS').exists())
        self.assertTrue(AccountProduct.objects.filter(product_code='CUR', product_type='CURRENT').exists())

    def test_minimum_balance_is_decimal(self):
        product = AccountProduct.objects.create(**self.product_data)
        self.assertIsInstance(product.minimum_balance, Decimal)
