from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.db.utils import IntegrityError
from branches.models import Branch
from users.models import StaffProfile
from customers.models import Customer
from products.models import AccountProduct
from accounts.models import Account
from transactions.models import Transaction
from users.services.branch_permission import (
    get_user_branch,
    can_access_account,
    can_approve_transaction,
)


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


class BranchPermissionServiceTest(TestCase):
    def setUp(self):
        # Branches
        self.branch_a = Branch.objects.create(
            branch_code="BR001",
            branch_name="Dhaka Main Branch",
            district="Dhaka",
            address="Motijheel C/A",
        )
        self.branch_b = Branch.objects.create(
            branch_code="BR002",
            branch_name="Chittagong Branch",
            district="Chittagong",
            address="Agrabad C/A",
        )
        self.inactive_branch = Branch.objects.create(
            branch_code="BR003",
            branch_name="Closed Branch",
            district="Sylhet",
            address="Zindabazar",
            is_active=False,
        )

        # Groups
        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.officer_group, _ = Group.objects.get_or_create(name='Officer')

        # Superuser
        self.superuser = User.objects.create_superuser(
            username="admin_user",
            email="admin@agranicbs.com",
            password="Password123!",
        )

        # Staff in Branch A
        self.staff_a = User.objects.create_user(
            username="staff_a",
            password="Password123!",
        )
        self.profile_a = StaffProfile.objects.create(
            user=self.staff_a,
            employee_id="EMP_A",
            branch=self.branch_a,
            is_active=True,
        )

        # Manager in Branch A
        self.manager_a = User.objects.create_user(
            username="manager_a",
            password="Password123!",
        )
        self.manager_a.groups.add(self.manager_group)
        self.profile_mgr_a = StaffProfile.objects.create(
            user=self.manager_a,
            employee_id="EMP_MGR_A",
            branch=self.branch_a,
            is_active=True,
        )

        # Manager in Branch B
        self.manager_b = User.objects.create_user(
            username="manager_b",
            password="Password123!",
        )
        self.manager_b.groups.add(self.manager_group)
        self.profile_mgr_b = StaffProfile.objects.create(
            user=self.manager_b,
            employee_id="EMP_MGR_B",
            branch=self.branch_b,
            is_active=True,
        )

        # Inactive staff
        self.inactive_user = User.objects.create_user(
            username="inactive_user",
            password="Password123!",
            is_active=False,
        )
        StaffProfile.objects.create(
            user=self.inactive_user,
            employee_id="EMP_INACTIVE",
            branch=self.branch_a,
            is_active=True,
        )

        # Staff with inactive profile
        self.user_inactive_profile = User.objects.create_user(
            username="user_inactive_profile",
            password="Password123!",
        )
        StaffProfile.objects.create(
            user=self.user_inactive_profile,
            employee_id="EMP_INACT_PROF",
            branch=self.branch_a,
            is_active=False,
        )

        # Staff in inactive branch
        self.user_in_inactive_branch = User.objects.create_user(
            username="user_in_inactive_branch",
            password="Password123!",
        )
        StaffProfile.objects.create(
            user=self.user_in_inactive_branch,
            employee_id="EMP_INACT_BR",
            branch=self.inactive_branch,
            is_active=True,
        )

        # User without staff profile
        self.plain_user = User.objects.create_user(
            username="plain_user",
            password="Password123!",
        )

        # Customer & Product & Accounts
        self.product = AccountProduct.objects.create(
            product_code="SAV01",
            product_name="Standard Savings",
            product_type=AccountProduct.ProductType.SAVINGS,
            minimum_balance=Decimal("500.00"),
            currency="BDT",
        )

        self.customer_a = Customer.objects.create(
            full_name="Customer Branch A",
            phone="01711111112",
            nid_number="NID10001",
            present_address="Dhaka",
            district="Dhaka",
            home_branch=self.branch_a,
            created_by=self.staff_a,
        )
        self.account_a = Account.objects.create(
            customer=self.customer_a,
            product=self.product,
            branch=self.branch_a,
            available_balance=Decimal("10000.00"),
            ledger_balance=Decimal("10000.00"),
        )

        self.customer_b = Customer.objects.create(
            full_name="Customer Branch B",
            phone="01711111113",
            nid_number="NID10002",
            present_address="Chittagong",
            district="Chittagong",
            home_branch=self.branch_b,
            created_by=self.manager_b,
        )
        self.account_b = Account.objects.create(
            customer=self.customer_b,
            product=self.product,
            branch=self.branch_b,
            available_balance=Decimal("20000.00"),
            ledger_balance=Decimal("20000.00"),
        )

        # Transactions
        self.txn_a = Transaction.objects.create(
            transaction_type=Transaction.TransactionType.DEPOSIT,
            account=self.account_a,
            amount=Decimal("1000.00"),
            created_by=self.staff_a,
        )

    def test_get_user_branch_valid_staff(self):
        self.assertEqual(get_user_branch(self.staff_a), self.branch_a)
        self.assertEqual(get_user_branch(self.manager_b), self.branch_b)

    def test_get_user_branch_none_or_unauthenticated(self):
        self.assertIsNone(get_user_branch(None))

    def test_get_user_branch_user_without_profile(self):
        self.assertIsNone(get_user_branch(self.plain_user))
        self.assertIsNone(get_user_branch(self.superuser))

    def test_get_user_branch_inactive_user_or_profile_or_branch(self):
        self.assertIsNone(get_user_branch(self.inactive_user))
        self.assertIsNone(get_user_branch(self.user_inactive_profile))
        self.assertIsNone(get_user_branch(self.user_in_inactive_branch))

    def test_can_access_account_superuser_bypass(self):
        self.assertTrue(can_access_account(self.superuser, self.account_a))
        self.assertTrue(can_access_account(self.superuser, self.account_b))

    def test_can_access_account_same_branch(self):
        self.assertTrue(can_access_account(self.staff_a, self.account_a))
        self.assertTrue(can_access_account(self.manager_a, self.account_a))
        self.assertTrue(can_access_account(self.manager_b, self.account_b))

    def test_can_access_account_different_branch(self):
        self.assertFalse(can_access_account(self.staff_a, self.account_b))
        self.assertFalse(can_access_account(self.manager_a, self.account_b))
        self.assertFalse(can_access_account(self.manager_b, self.account_a))

    def test_can_access_account_invalid_inputs(self):
        self.assertFalse(can_access_account(None, self.account_a))
        self.assertFalse(can_access_account(self.staff_a, None))
        self.assertFalse(can_access_account(self.plain_user, self.account_a))
        self.assertFalse(can_access_account(self.inactive_user, self.account_a))

    def test_can_approve_transaction_superuser_bypass(self):
        self.assertTrue(can_approve_transaction(self.superuser, self.txn_a))

    def test_can_approve_transaction_manager_same_branch(self):
        self.assertTrue(can_approve_transaction(self.manager_a, self.txn_a))

    def test_can_approve_transaction_manager_different_branch(self):
        self.assertFalse(can_approve_transaction(self.manager_b, self.txn_a))

    def test_can_approve_transaction_non_manager(self):
        # staff_a is in Branch A but not in Manager group
        self.assertFalse(can_approve_transaction(self.staff_a, self.txn_a))

    def test_can_approve_transaction_invalid_inputs(self):
        self.assertFalse(can_approve_transaction(None, self.txn_a))
        self.assertFalse(can_approve_transaction(self.manager_a, None))
        self.assertFalse(can_approve_transaction(self.inactive_user, self.txn_a))


from django.test import Client
from users.views import get_user_role, get_user_staff_info, get_role_redirect_url


class CBSAuthenticationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.branch = Branch.objects.create(
            branch_code="BR100",
            branch_name="Motijheel Corporate",
            district="Dhaka",
            address="Motijheel C/A",
            is_active=True,
        )

        self.teller_group, _ = Group.objects.get_or_create(name='Teller')
        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.auditor_group, _ = Group.objects.get_or_create(name='Auditor')

        # 1. Teller
        self.teller_user = User.objects.create_user(
            username="cbs_teller",
            password="TellerPassword123!",
            first_name="Tariq",
            last_name="Islam",
        )
        self.teller_user.groups.add(self.teller_group)
        self.teller_profile = StaffProfile.objects.create(
            user=self.teller_user,
            employee_id="EMP_TEL_01",
            branch=self.branch,
            designation="Cash Officer",
            is_active=True,
        )

        # 2. Manager
        self.manager_user = User.objects.create_user(
            username="cbs_manager",
            password="ManagerPassword123!",
            first_name="Hasina",
            last_name="Begum",
        )
        self.manager_user.groups.add(self.manager_group)
        self.manager_profile = StaffProfile.objects.create(
            user=self.manager_user,
            employee_id="EMP_MGR_01",
            branch=self.branch,
            designation="Branch Manager",
            is_active=True,
        )

        # 3. Auditor
        self.auditor_user = User.objects.create_user(
            username="cbs_auditor",
            password="AuditorPassword123!",
            first_name="Kamal",
            last_name="Hossain",
        )
        self.auditor_user.groups.add(self.auditor_group)
        self.auditor_profile = StaffProfile.objects.create(
            user=self.auditor_user,
            employee_id="EMP_AUD_01",
            branch=self.branch,
            designation="Internal Auditor",
            is_active=True,
        )

        # 4. Inactive user
        self.inactive_user = User.objects.create_user(
            username="cbs_inactive",
            password="InactivePassword123!",
            is_active=False,
        )
        self.inactive_user.groups.add(self.teller_group)
        self.inactive_profile = StaffProfile.objects.create(
            user=self.inactive_user,
            employee_id="EMP_INACT_01",
            branch=self.branch,
            is_active=True,
        )

    def test_login_page_renders_get_request(self):
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/login.html')

    def test_valid_login_teller_redirects_to_teller_dashboard(self):
        response = self.client.post('/login/', {
            'username': 'cbs_teller',
            'password': 'TellerPassword123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/teller/')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.teller_user.id)

    def test_valid_login_manager_redirects_to_manager_dashboard(self):
        response = self.client.post('/login/', {
            'username': 'cbs_manager',
            'password': 'ManagerPassword123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/manager/')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.manager_user.id)

    def test_valid_login_auditor_redirects_to_auditor_dashboard(self):
        response = self.client.post('/login/', {
            'username': 'cbs_auditor',
            'password': 'AuditorPassword123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/auditor/')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.auditor_user.id)

    def test_invalid_password_fails_login(self):
        response = self.client.post('/login/', {
            'username': 'cbs_teller',
            'password': 'WrongPassword999!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', response.wsgi_request.session.keys() if hasattr(response, 'wsgi_request') else [])
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(response, "Invalid username or password")

    def test_inactive_user_blocked(self):
        response = self.client.post('/login/', {
            'username': 'cbs_inactive',
            'password': 'InactivePassword123!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(response, "inactive")

    def test_role_detection_from_groups(self):
        self.assertEqual(get_user_role(self.teller_user), 'Teller')
        self.assertEqual(get_user_role(self.manager_user), 'Manager')
        self.assertEqual(get_user_role(self.auditor_user), 'Auditor')

        self.assertEqual(get_role_redirect_url(self.teller_user), '/dashboard/teller/')
        self.assertEqual(get_role_redirect_url(self.manager_user), '/dashboard/manager/')
        self.assertEqual(get_role_redirect_url(self.auditor_user), '/dashboard/auditor/')

    def test_staff_profile_and_branch_detection(self):
        profile, branch = get_user_staff_info(self.teller_user)
        self.assertEqual(profile, self.teller_profile)
        self.assertEqual(branch, self.branch)

        mgr_profile, mgr_branch = get_user_staff_info(self.manager_user)
        self.assertEqual(mgr_profile, self.manager_profile)
        self.assertEqual(mgr_branch, self.branch)

    def test_logout_view(self):
        # First log in
        self.client.login(username='cbs_teller', password='TellerPassword123!')
        self.assertIn('_auth_user_id', self.client.session)

        # Log out
        response = self.client.get('/logout/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/login/')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_authenticated_user_accessing_login_redirects(self):
        self.client.login(username='cbs_teller', password='TellerPassword123!')
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/dashboard/teller/')

