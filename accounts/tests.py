from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from branches.models import Branch
from customers.models import Customer
from products.models import AccountProduct
from accounts.models import Account


class AccountModelTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
            is_active=True,
        )
        self.staff_user = User.objects.create_user(username="officer1", password="Password123!")

        self.customer = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Rahim Uddin",
            date_of_birth=date(1985, 3, 20),
            nid_number="1985123456789",
            phone="01811111111",
            present_address="45 Gulshan, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.staff_user,
            status=Customer.Status.ACTIVE,
        )
        self.product = AccountProduct.objects.get(product_code="SAV")
        self.account_data = {
            "customer": self.customer,
            "product": self.product,
            "branch": self.branch,
        }

    def test_account_creation(self):
        account = Account.objects.create(**self.account_data)
        self.assertTrue(account.account_number.startswith("ACC"))
        self.assertEqual(len(account.account_number), 11)  # ACC + 8 digits
        self.assertEqual(account.customer, self.customer)
        self.assertEqual(account.product, self.product)
        self.assertEqual(account.branch, self.branch)
        self.assertEqual(account.currency, "BDT")
        self.assertEqual(account.available_balance, Decimal("0.00"))
        self.assertEqual(account.ledger_balance, Decimal("0.00"))
        self.assertEqual(account.account_status, Account.AccountStatus.ACTIVE)
        self.assertIsNotNone(account.opening_date)
        self.assertIsNotNone(account.created_at)

    def test_automatic_account_number_generation(self):
        a1 = Account.objects.create(**self.account_data)
        a2 = Account.objects.create(**self.account_data)

        # Both must start with ACC and have 8-digit zero-padded suffix
        self.assertRegex(a1.account_number, r'^ACC\d{8}$')
        self.assertRegex(a2.account_number, r'^ACC\d{8}$')

        # Must be unique
        self.assertNotEqual(a1.account_number, a2.account_number)

        # Must be ascending (sequential)
        self.assertLess(int(a1.account_number[3:]), int(a2.account_number[3:]))

    def test_unique_account_number(self):
        a1 = Account.objects.create(**self.account_data)
        a2 = Account.objects.create(**self.account_data)
        all_numbers = list(Account.objects.values_list("account_number", flat=True))
        self.assertEqual(len(all_numbers), len(set(all_numbers)))

    def test_customer_relationship(self):
        account = Account.objects.create(**self.account_data)
        self.assertIn(account, self.customer.accounts.all())

    def test_product_relationship(self):
        account = Account.objects.create(**self.account_data)
        self.assertIn(account, self.product.accounts.all())

    def test_branch_relationship(self):
        account = Account.objects.create(**self.account_data)
        self.assertIn(account, self.branch.accounts.all())

    def test_inactive_customer_rejection(self):
        self.customer.status = Customer.Status.INACTIVE
        self.customer.save()
        account = Account(**self.account_data)
        with self.assertRaises(ValidationError) as ctx:
            account.save()
        self.assertIn("customer", ctx.exception.message_dict)

    def test_inactive_product_rejection(self):
        self.product.is_active = False
        self.product.save()
        account = Account(**self.account_data)
        with self.assertRaises(ValidationError) as ctx:
            account.save()
        self.assertIn("product", ctx.exception.message_dict)
