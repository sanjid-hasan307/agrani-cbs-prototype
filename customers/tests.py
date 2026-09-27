from datetime import date, timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.contrib.auth.models import User
from branches.models import Branch
from customers.models import Customer


class CustomerModelTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
        )
        self.staff_user = User.objects.create_user(
            username="officer1",
            password="Password123!",
        )
        self.customer_data = {
            "customer_type": Customer.CustomerType.INDIVIDUAL,
            "full_name": "Karim Rahman",
            "date_of_birth": date(1990, 5, 15),
            "gender": Customer.Gender.MALE,
            "nid_number": "1990123456789",
            "phone": "01712345678",
            "present_address": "12 Green Road, Dhaka",
            "district": "Dhaka",
            "home_branch": self.branch,
            "created_by": self.staff_user,
        }

    def test_successful_customer_creation(self):
        customer = Customer.objects.create(**self.customer_data)
        self.assertTrue(customer.cif_number.startswith("CIF"))
        self.assertEqual(customer.full_name, "Karim Rahman")
        self.assertEqual(customer.home_branch, self.branch)
        self.assertEqual(customer.created_by, self.staff_user)
        self.assertEqual(customer.status, Customer.Status.ACTIVE)
        self.assertEqual(customer.kyc_status, Customer.KYCStatus.PENDING)
        self.assertEqual(customer.risk_level, Customer.RiskLevel.LOW)
        self.assertIsNotNone(customer.created_at)
        self.assertIsNotNone(customer.updated_at)

    def test_automatic_cif_generation_and_uniqueness(self):
        c1 = Customer.objects.create(**self.customer_data)

        data2 = self.customer_data.copy()
        data2["nid_number"] = "1990987654321"
        c2 = Customer.objects.create(**data2)

        data3 = self.customer_data.copy()
        data3["nid_number"] = "1990111222333"
        c3 = Customer.objects.create(**data3)

        # All must match CIF + 8 digits format
        self.assertRegex(c1.cif_number, r'^CIF\d{8}$')
        self.assertRegex(c2.cif_number, r'^CIF\d{8}$')
        self.assertRegex(c3.cif_number, r'^CIF\d{8}$')

        # All must be unique
        self.assertEqual(len({c1.cif_number, c2.cif_number, c3.cif_number}), 3)

        # Must be ascending (sequential)
        self.assertLess(int(c1.cif_number[3:]), int(c2.cif_number[3:]))
        self.assertLess(int(c2.cif_number[3:]), int(c3.cif_number[3:]))

    def test_branch_and_created_by_relationships(self):
        customer = Customer.objects.create(**self.customer_data)
        self.assertIn(customer, self.branch.customers.all())
        self.assertIn(customer, self.staff_user.created_customers.all())

    def test_future_date_of_birth_rejection(self):
        invalid_data = self.customer_data.copy()
        invalid_data["date_of_birth"] = date.today() + timedelta(days=1)
        customer = Customer(**invalid_data)
        with self.assertRaises(ValidationError) as ctx:
            customer.save()
        self.assertIn("date_of_birth", ctx.exception.message_dict)

    def test_required_identity_document_validation(self):
        # INDIVIDUAL customer without NID or passport must fail
        invalid_data = self.customer_data.copy()
        invalid_data["nid_number"] = None
        invalid_data["passport_number"] = None
        customer = Customer(**invalid_data)
        with self.assertRaises(ValidationError) as ctx:
            customer.save()
        self.assertIn("nid_number", ctx.exception.message_dict)

        # ORGANIZATION customer without NID or passport is allowed
        org_data = self.customer_data.copy()
        org_data["customer_type"] = Customer.CustomerType.ORGANIZATION
        org_data["nid_number"] = None
        org_data["passport_number"] = None
        org_customer = Customer.objects.create(**org_data)
        self.assertIsNotNone(org_customer.cif_number)

    def test_string_representation(self):
        customer = Customer.objects.create(**self.customer_data)
        expected_str = f"{customer.cif_number} - Karim Rahman"
        self.assertEqual(str(customer), expected_str)

    def test_unique_nid_number_enforcement(self):
        Customer.objects.create(**self.customer_data)
        duplicate_data = self.customer_data.copy()
        duplicate_customer = Customer(**duplicate_data)
        with self.assertRaises((IntegrityError, ValidationError)):
            duplicate_customer.save()
