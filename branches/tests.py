from django.test import TestCase
from django.db.utils import IntegrityError
from branches.models import Branch


class BranchModelTest(TestCase):
    def setUp(self):
        self.branch_data = {
            "branch_code": "BR001",
            "branch_name": "Main Branch",
            "routing_number": "RT1001",
            "address": "123 Main St",
            "district": "Dhaka",
            "phone": "01700000000",
            "email": "main@agranicbs.com",
            "is_active": True,
        }

    def test_successful_branch_creation(self):
        branch = Branch.objects.create(**self.branch_data)
        self.assertEqual(branch.branch_code, "BR001")
        self.assertEqual(branch.branch_name, "Main Branch")
        self.assertEqual(branch.routing_number, "RT1001")
        self.assertEqual(branch.district, "Dhaka")
        self.assertTrue(branch.is_active)
        self.assertIsNotNone(branch.created_at)
        self.assertIsNotNone(branch.updated_at)

    def test_unique_branch_code_enforcement(self):
        Branch.objects.create(**self.branch_data)
        duplicate_branch = Branch(
            branch_code="BR001",  # Same code
            branch_name="Duplicate Branch",
            routing_number="RT1002",
            address="456 Secondary St",
            district="Chittagong",
        )
        with self.assertRaises(IntegrityError):
            duplicate_branch.save()

    def test_string_representation(self):
        branch = Branch.objects.create(**self.branch_data)
        expected_str = f"{branch.branch_code} - {branch.branch_name}"
        self.assertEqual(str(branch), expected_str)
