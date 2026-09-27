from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.db.utils import IntegrityError
from branches.models import Branch
from users.models import StaffProfile


class StaffProfileModelTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
        )
        self.user = User.objects.create_user(
            username="teststaff",
            email="teststaff@agranicbs.com",
            password="Password123!",
            first_name="Rahim",
            last_name="Uddin",
        )
        self.staff_data = {
            "user": self.user,
            "employee_id": "EMP10001",
            "branch": self.branch,
            "designation": "Senior Officer",
            "phone": "01711111111",
            "is_active": True,
        }

    def test_staff_profile_creation(self):
        profile = StaffProfile.objects.create(**self.staff_data)
        self.assertEqual(profile.employee_id, "EMP10001")
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.branch, self.branch)
        self.assertEqual(profile.designation, "Senior Officer")
        self.assertTrue(profile.is_active)
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.updated_at)

    def test_user_profile_relationship(self):
        profile = StaffProfile.objects.create(**self.staff_data)
        self.assertEqual(self.user.staff_profile, profile)
        self.assertEqual(str(profile), "EMP10001 - Rahim Uddin")

    def test_branch_relationship(self):
        profile = StaffProfile.objects.create(**self.staff_data)
        self.assertIn(profile, self.branch.staff_members.all())

    def test_unique_employee_id_enforcement(self):
        StaffProfile.objects.create(**self.staff_data)
        user2 = User.objects.create_user(username="teststaff2")
        duplicate_profile = StaffProfile(
            user=user2,
            employee_id="EMP10001",  # Duplicate ID
            branch=self.branch,
        )
        with self.assertRaises(IntegrityError):
            duplicate_profile.save()

    def test_five_required_groups_exist(self):
        expected_roles = ["Admin", "Manager", "Officer", "Teller", "Auditor"]
        for role_name in expected_roles:
            self.assertTrue(
                Group.objects.filter(name=role_name).exists(),
                f"Group '{role_name}' does not exist.",
            )
