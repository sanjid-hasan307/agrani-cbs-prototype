from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.db.utils import IntegrityError
from branches.models import Branch
from users.models import StaffProfile
from customers.models import Customer
from products.models import AccountProduct
from accounts.models import Account
from audit.models import AuditLog
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



# =============================================================================
# Phase 4 — Dashboard Access Tests
# =============================================================================

class DashboardAccessTest(TestCase):
    """
    Tests for CBS role-based dashboard access control.

    Verifies:
    - Each role can access its own dashboard (200 OK, correct template).
    - Each role is denied access to another role's dashboard (403 Forbidden).
    - Unauthenticated requests are redirected to /login/.
    """

    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR200",
            branch_name="Dashboard Test Branch",
            district="Chittagong",
            address="Agrabad C/A",
            is_active=True,
        )

        self.manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.teller_group, _ = Group.objects.get_or_create(name="Teller")
        self.auditor_group, _ = Group.objects.get_or_create(name="Auditor")

        # Manager
        self.manager_user = User.objects.create_user(
            username="dash_manager",
            password="ManagerPass123!",
            first_name="Fatema",
            last_name="Khanam",
        )
        self.manager_user.groups.add(self.manager_group)
        StaffProfile.objects.create(
            user=self.manager_user,
            employee_id="EMP_D_MGR",
            branch=self.branch,
            designation="Branch Manager",
            is_active=True,
        )

        # Teller
        self.teller_user = User.objects.create_user(
            username="dash_teller",
            password="TellerPass123!",
            first_name="Rafiq",
            last_name="Ahmed",
        )
        self.teller_user.groups.add(self.teller_group)
        StaffProfile.objects.create(
            user=self.teller_user,
            employee_id="EMP_D_TEL",
            branch=self.branch,
            designation="Teller Officer",
            is_active=True,
        )

        # Auditor
        self.auditor_user = User.objects.create_user(
            username="dash_auditor",
            password="AuditorPass123!",
            first_name="Nasrin",
            last_name="Sultana",
        )
        self.auditor_user.groups.add(self.auditor_group)
        StaffProfile.objects.create(
            user=self.auditor_user,
            employee_id="EMP_D_AUD",
            branch=self.branch,
            designation="Internal Auditor",
            is_active=True,
        )

    # ------------------------------------------------------------------
    # Manager dashboard
    # ------------------------------------------------------------------

    def test_manager_can_access_manager_dashboard(self):
        self.client.login(username="dash_manager", password="ManagerPass123!")
        response = self.client.get("/dashboard/manager/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/dashboard_manager.html")
        self.assertContains(response, "Manager")

    def test_manager_dashboard_shows_username(self):
        self.client.login(username="dash_manager", password="ManagerPass123!")
        response = self.client.get("/dashboard/manager/")
        self.assertContains(response, "Fatema")

    def test_manager_dashboard_shows_branch(self):
        self.client.login(username="dash_manager", password="ManagerPass123!")
        response = self.client.get("/dashboard/manager/")
        self.assertContains(response, "Dashboard Test Branch")

    # ------------------------------------------------------------------
    # Teller dashboard
    # ------------------------------------------------------------------

    def test_teller_can_access_teller_dashboard(self):
        self.client.login(username="dash_teller", password="TellerPass123!")
        response = self.client.get("/dashboard/teller/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/dashboard_teller.html")
        self.assertContains(response, "Teller")

    def test_teller_dashboard_shows_username(self):
        self.client.login(username="dash_teller", password="TellerPass123!")
        response = self.client.get("/dashboard/teller/")
        self.assertContains(response, "Rafiq")

    def test_teller_dashboard_shows_branch(self):
        self.client.login(username="dash_teller", password="TellerPass123!")
        response = self.client.get("/dashboard/teller/")
        self.assertContains(response, "Dashboard Test Branch")

    # ------------------------------------------------------------------
    # Auditor dashboard
    # ------------------------------------------------------------------

    def test_auditor_can_access_auditor_dashboard(self):
        self.client.login(username="dash_auditor", password="AuditorPass123!")
        response = self.client.get("/dashboard/auditor/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/dashboard_auditor.html")
        self.assertContains(response, "Auditor")

    def test_auditor_dashboard_shows_username(self):
        self.client.login(username="dash_auditor", password="AuditorPass123!")
        response = self.client.get("/dashboard/auditor/")
        self.assertContains(response, "Nasrin")

    def test_auditor_dashboard_shows_branch(self):
        self.client.login(username="dash_auditor", password="AuditorPass123!")
        response = self.client.get("/dashboard/auditor/")
        self.assertContains(response, "Dashboard Test Branch")

    # ------------------------------------------------------------------
    # Cross-role access is blocked (403)
    # ------------------------------------------------------------------

    def test_teller_cannot_access_manager_dashboard(self):
        self.client.login(username="dash_teller", password="TellerPass123!")
        response = self.client.get("/dashboard/manager/")
        self.assertEqual(response.status_code, 403)

    def test_teller_cannot_access_auditor_dashboard(self):
        self.client.login(username="dash_teller", password="TellerPass123!")
        response = self.client.get("/dashboard/auditor/")
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_access_teller_dashboard(self):
        self.client.login(username="dash_manager", password="ManagerPass123!")
        response = self.client.get("/dashboard/teller/")
        self.assertEqual(response.status_code, 403)

    def test_manager_cannot_access_auditor_dashboard(self):
        self.client.login(username="dash_manager", password="ManagerPass123!")
        response = self.client.get("/dashboard/auditor/")
        self.assertEqual(response.status_code, 403)

    def test_auditor_cannot_access_manager_dashboard(self):
        self.client.login(username="dash_auditor", password="AuditorPass123!")
        response = self.client.get("/dashboard/manager/")
        self.assertEqual(response.status_code, 403)

    def test_auditor_cannot_access_teller_dashboard(self):
        self.client.login(username="dash_auditor", password="AuditorPass123!")
        response = self.client.get("/dashboard/teller/")
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # Unauthenticated access redirects to login
    # ------------------------------------------------------------------

    def test_unauthenticated_manager_dashboard_redirects_to_login(self):
        response = self.client.get("/dashboard/manager/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_unauthenticated_teller_dashboard_redirects_to_login(self):
        response = self.client.get("/dashboard/teller/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_unauthenticated_auditor_dashboard_redirects_to_login(self):
        response = self.client.get("/dashboard/auditor/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


# =============================================================================
# Phase 5 — Manager Approval Dashboard Integration Tests
# =============================================================================

class ManagerApprovalDashboardTest(TestCase):
    """
    Tests for Phase 5: Manager Approval Dashboard Integration.

    Verifies:
    - Manager sees pending transactions for own branch only.
    - Manager cannot see pending transactions from other branches.
    - Manager can approve pending transactions from dashboard.
    - Manager can reject pending transactions from dashboard with rejection reason.
    - Teller cannot access approval or rejection endpoints (403 Forbidden).
    - Manager cannot approve or reject transactions from other branches (403 Forbidden).
    """

    def setUp(self):
        # Roles
        self.manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.teller_group, _ = Group.objects.get_or_create(name="Teller")

        # Branches
        self.branch_a = Branch.objects.create(
            branch_code="BR501",
            branch_name="Agrabad Branch",
            district="Chittagong",
            address="Agrabad C/A",
            is_active=True,
        )
        self.branch_b = Branch.objects.create(
            branch_code="BR502",
            branch_name="Motijheel Branch",
            district="Dhaka",
            address="Motijheel C/A",
            is_active=True,
        )

        # Manager A (Branch A)
        self.manager_a = User.objects.create_user(
            username="manager_agrabad",
            password="ManagerPass123!",
            first_name="Fatema",
            last_name="Manager",
        )
        self.manager_a.groups.add(self.manager_group)
        StaffProfile.objects.create(
            user=self.manager_a,
            employee_id="EMP_MGR_A",
            branch=self.branch_a,
            designation="Branch Manager",
            is_active=True,
        )

        # Teller A (Branch A)
        self.teller_a = User.objects.create_user(
            username="teller_agrabad",
            password="TellerPass123!",
            first_name="Rafiq",
            last_name="Teller",
        )
        self.teller_a.groups.add(self.teller_group)
        StaffProfile.objects.create(
            user=self.teller_a,
            employee_id="EMP_TEL_A",
            branch=self.branch_a,
            designation="Teller Officer",
            is_active=True,
        )

        # Teller B (Branch B)
        self.teller_b = User.objects.create_user(
            username="teller_motijheel",
            password="TellerPass123!",
            first_name="Kamal",
            last_name="Teller",
        )
        self.teller_b.groups.add(self.teller_group)
        StaffProfile.objects.create(
            user=self.teller_b,
            employee_id="EMP_TEL_B",
            branch=self.branch_b,
            designation="Teller Officer",
            is_active=True,
        )

        # Product
        self.product = AccountProduct.objects.create(
            product_code="SAV500",
            product_name="Savings Phase 5",
            product_type=AccountProduct.ProductType.SAVINGS,
            minimum_balance=Decimal("500.00"),
            currency="BDT",
        )

        # Customer & Account A (Branch A)
        self.customer_a = Customer.objects.create(
            full_name="Agrabad Customer",
            phone="01711111190",
            nid_number="NID5001",
            present_address="Chittagong",
            district="Chittagong",
            home_branch=self.branch_a,
            created_by=self.teller_a,
        )
        self.account_a = Account.objects.create(
            customer=self.customer_a,
            product=self.product,
            branch=self.branch_a,
            available_balance=Decimal("10000.00"),
            ledger_balance=Decimal("10000.00"),
        )

        # Customer & Account B (Branch B)
        self.customer_b = Customer.objects.create(
            full_name="Motijheel Customer",
            phone="01711111191",
            nid_number="NID5002",
            present_address="Dhaka",
            district="Dhaka",
            home_branch=self.branch_b,
            created_by=self.teller_b,
        )
        self.account_b = Account.objects.create(
            customer=self.customer_b,
            product=self.product,
            branch=self.branch_b,
            available_balance=Decimal("20000.00"),
            ledger_balance=Decimal("20000.00"),
        )

    def test_manager_sees_pending_transactions_from_own_branch(self):
        from transactions.services.deposit_service import deposit
        txn_a = deposit(
            account=self.account_a,
            amount=Decimal("5000.00"),
            created_by=self.teller_a,
            description="Branch A pending deposit",
        )

        self.client.login(username="manager_agrabad", password="ManagerPass123!")
        response = self.client.get("/dashboard/manager/")
        self.assertEqual(response.status_code, 200)

        # Check pending transactions in context
        pending_list = list(response.context["pending_transactions"])
        self.assertIn(txn_a, pending_list)
        self.assertEqual(response.context["pending_count"], 1)

        # Check details displayed in HTML
        self.assertContains(response, txn_a.transaction_id)
        self.assertContains(response, "5000.00")
        self.assertContains(response, "teller_agrabad")

    def test_manager_cannot_see_other_branch_transactions(self):
        from transactions.services.deposit_service import deposit
        # Pending deposit in branch A
        txn_a = deposit(
            account=self.account_a,
            amount=Decimal("3000.00"),
            created_by=self.teller_a,
            description="Branch A deposit",
        )
        # Pending deposit in branch B
        txn_b = deposit(
            account=self.account_b,
            amount=Decimal("7000.00"),
            created_by=self.teller_b,
            description="Branch B deposit",
        )

        self.client.login(username="manager_agrabad", password="ManagerPass123!")
        response = self.client.get("/dashboard/manager/")
        self.assertEqual(response.status_code, 200)

        pending_list = list(response.context["pending_transactions"])
        self.assertIn(txn_a, pending_list)
        self.assertNotIn(txn_b, pending_list)
        self.assertEqual(response.context["pending_count"], 1)
        self.assertNotContains(response, txn_b.transaction_id)

    def test_manager_can_approve_from_dashboard(self):
        from transactions.services.deposit_service import deposit
        txn_a = deposit(
            account=self.account_a,
            amount=Decimal("4000.00"),
            created_by=self.teller_a,
            description="Deposit to approve",
        )
        self.assertEqual(txn_a.authorization_status, Transaction.AuthorizationStatus.PENDING)

        self.client.login(username="manager_agrabad", password="ManagerPass123!")
        response = self.client.post(f"/dashboard/manager/approve/{txn_a.id}/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard/manager/", response.url)

        txn_a.refresh_from_db()
        self.assertEqual(txn_a.authorization_status, Transaction.AuthorizationStatus.APPROVED)
        self.assertEqual(txn_a.status, Transaction.Status.POSTED)
        self.assertEqual(txn_a.approved_by, self.manager_a)

        self.account_a.refresh_from_db()
        self.assertEqual(self.account_a.available_balance, Decimal("14000.00"))

    def test_manager_can_reject_from_dashboard(self):
        from transactions.services.deposit_service import deposit
        txn_a = deposit(
            account=self.account_a,
            amount=Decimal("2500.00"),
            created_by=self.teller_a,
            description="Deposit to reject",
        )
        self.assertEqual(txn_a.authorization_status, Transaction.AuthorizationStatus.PENDING)

        self.client.login(username="manager_agrabad", password="ManagerPass123!")
        response = self.client.post(
            f"/dashboard/manager/reject/{txn_a.id}/",
            data={"rejection_reason": "Incomplete documentation"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard/manager/", response.url)

        txn_a.refresh_from_db()
        self.assertEqual(txn_a.authorization_status, Transaction.AuthorizationStatus.REJECTED)
        self.assertEqual(txn_a.status, Transaction.Status.REJECTED)
        self.assertEqual(txn_a.approved_by, self.manager_a)
        self.assertEqual(txn_a.rejection_reason, "Incomplete documentation")

        # Balance remains unchanged
        self.account_a.refresh_from_db()
        self.assertEqual(self.account_a.available_balance, Decimal("10000.00"))

    def test_teller_cannot_access_approval_actions(self):
        from transactions.services.deposit_service import deposit
        txn_a = deposit(
            account=self.account_a,
            amount=Decimal("1500.00"),
            created_by=self.teller_a,
            description="Deposit attempt teller approval",
        )

        self.client.login(username="teller_agrabad", password="TellerPass123!")

        # Attempt approve -> 403 Forbidden
        response_approve = self.client.post(f"/dashboard/manager/approve/{txn_a.id}/")
        self.assertEqual(response_approve.status_code, 403)

        # Attempt reject -> 403 Forbidden
        response_reject = self.client.post(
            f"/dashboard/manager/reject/{txn_a.id}/",
            data={"rejection_reason": "Unauthorized reject attempt"},
        )
        self.assertEqual(response_reject.status_code, 403)

        # Ensure transaction is still pending
        txn_a.refresh_from_db()
        self.assertEqual(txn_a.authorization_status, Transaction.AuthorizationStatus.PENDING)

    def test_manager_cannot_approve_other_branch_transaction(self):
        from transactions.services.deposit_service import deposit
        txn_b = deposit(
            account=self.account_b,
            amount=Decimal("2000.00"),
            created_by=self.teller_b,
            description="Branch B deposit",
        )

        self.client.login(username="manager_agrabad", password="ManagerPass123!")
        response = self.client.post(f"/dashboard/manager/approve/{txn_b.id}/")
        self.assertEqual(response.status_code, 403)

        txn_b.refresh_from_db()
        self.assertEqual(txn_b.authorization_status, Transaction.AuthorizationStatus.PENDING)

    def test_manager_cannot_reject_other_branch_transaction(self):
        from transactions.services.deposit_service import deposit
        txn_b = deposit(
            account=self.account_b,
            amount=Decimal("2000.00"),
            created_by=self.teller_b,
            description="Branch B deposit",
        )

        self.client.login(username="manager_agrabad", password="ManagerPass123!")
        response = self.client.post(
            f"/dashboard/manager/reject/{txn_b.id}/",
            data={"rejection_reason": "Cross branch attempt"},
        )
        self.assertEqual(response.status_code, 403)

        txn_b.refresh_from_db()
        self.assertEqual(txn_b.authorization_status, Transaction.AuthorizationStatus.PENDING)


# =============================================================================
# Phase 1 — Teller Cash Deposit Integration Tests
# =============================================================================

class TellerDepositDashboardTest(TestCase):
    """
    Tests for Teller Cash Deposit endpoint (/dashboard/teller/deposit/).

    Verifies:
    - Valid deposit creates PENDING transaction and leaves balances unchanged.
    - Deposit cannot be made for an account in a different branch.
    - Invalid account numbers or non-numeric/negative amounts set error message cleanly.
    - Non-Teller roles (Manager, Auditor) are denied with HTTP 403.
    - Unauthenticated requests redirect to /login/.
    - GET method returns 405 Method Not Allowed.
    """

    def setUp(self):
        self.branch_a = Branch.objects.create(
            branch_code="BR601",
            branch_name="Motijheel Branch",
            district="Dhaka",
            address="Motijheel C/A",
            is_active=True,
        )
        self.branch_b = Branch.objects.create(
            branch_code="BR602",
            branch_name="Agrabad Branch",
            district="Chittagong",
            address="Agrabad C/A",
            is_active=True,
        )

        self.teller_group, _ = Group.objects.get_or_create(name="Teller")
        self.manager_group, _ = Group.objects.get_or_create(name="Manager")

        # Teller in Branch A
        self.teller_user = User.objects.create_user(
            username="teller_dhaka",
            password="TellerPassword123!",
            first_name="Tariq",
            last_name="Islam",
        )
        self.teller_user.groups.add(self.teller_group)
        StaffProfile.objects.create(
            user=self.teller_user,
            employee_id="EMP_TEL_DHAKA",
            branch=self.branch_a,
            designation="Cash Teller",
            is_active=True,
        )

        # Manager in Branch A
        self.manager_user = User.objects.create_user(
            username="manager_dhaka",
            password="ManagerPassword123!",
        )
        self.manager_user.groups.add(self.manager_group)
        StaffProfile.objects.create(
            user=self.manager_user,
            employee_id="EMP_MGR_DHAKA",
            branch=self.branch_a,
            designation="Branch Manager",
            is_active=True,
        )

        # Account Product
        self.product = AccountProduct.objects.create(
            product_code="SAV600",
            product_name="Savings Account",
            product_type=AccountProduct.ProductType.SAVINGS,
            minimum_balance=Decimal("500.00"),
            currency="BDT",
        )

        # Customer & Account in Branch A
        self.customer_a = Customer.objects.create(
            full_name="Dhaka Customer",
            phone="01700000001",
            nid_number="NID6001",
            present_address="Dhaka",
            district="Dhaka",
            home_branch=self.branch_a,
            created_by=self.teller_user,
        )
        self.account_a = Account.objects.create(
            customer=self.customer_a,
            product=self.product,
            branch=self.branch_a,
            account_number="AC60001",
            available_balance=Decimal("5000.00"),
            ledger_balance=Decimal("5000.00"),
        )

        # Customer & Account in Branch B
        self.customer_b = Customer.objects.create(
            full_name="Chittagong Customer",
            phone="01700000002",
            nid_number="NID6002",
            present_address="Chittagong",
            district="Chittagong",
            home_branch=self.branch_b,
            created_by=self.teller_user,
        )
        self.account_b = Account.objects.create(
            customer=self.customer_b,
            product=self.product,
            branch=self.branch_b,
            account_number="AC60002",
            available_balance=Decimal("10000.00"),
            ledger_balance=Decimal("10000.00"),
        )

    def test_teller_can_create_deposit_successfully(self):
        self.client.login(username="teller_dhaka", password="TellerPassword123!")
        response = self.client.post("/dashboard/teller/deposit/", {
            "account_number": "AC60001",
            "amount": "2500.50",
            "description": "Counter Cash Deposit",
        })
        # Should redirect back to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/teller/")

        # Verify transaction created in DB
        txn = Transaction.objects.get(account=self.account_a)
        self.assertEqual(txn.amount, Decimal("2500.50"))
        self.assertEqual(txn.transaction_type, Transaction.TransactionType.DEPOSIT)
        self.assertEqual(txn.authorization_status, Transaction.AuthorizationStatus.PENDING)
        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.created_by, self.teller_user)

        # Verify account balances remain UNCHANGED until Manager approval
        self.account_a.refresh_from_db()
        self.assertEqual(self.account_a.available_balance, Decimal("5000.00"))
        self.assertEqual(self.account_a.ledger_balance, Decimal("5000.00"))

    def test_teller_cannot_deposit_to_different_branch_account(self):
        self.client.login(username="teller_dhaka", password="TellerPassword123!")
        response = self.client.post("/dashboard/teller/deposit/", {
            "account_number": "AC60002",  # Branch B account
            "amount": "1000.00",
            "description": "Cross branch deposit attempt",
        })
        self.assertEqual(response.status_code, 302)

        # Ensure transaction was NOT created
        self.assertFalse(Transaction.objects.filter(account=self.account_b).exists())

        # Ensure balance unchanged
        self.account_b.refresh_from_db()
        self.assertEqual(self.account_b.available_balance, Decimal("10000.00"))

    def test_teller_deposit_nonexistent_account_shows_error(self):
        self.client.login(username="teller_dhaka", password="TellerPassword123!")
        response = self.client.post("/dashboard/teller/deposit/", {
            "account_number": "AC99999",
            "amount": "1000.00",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_teller_deposit_invalid_amount_format(self):
        self.client.login(username="teller_dhaka", password="TellerPassword123!")
        response = self.client.post("/dashboard/teller/deposit/", {
            "account_number": "AC60001",
            "amount": "abc_invalid",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_teller_deposit_negative_amount_fails(self):
        self.client.login(username="teller_dhaka", password="TellerPassword123!")
        response = self.client.post("/dashboard/teller/deposit/", {
            "account_number": "AC60001",
            "amount": "-500.00",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_non_teller_denied_access_to_deposit_endpoint(self):
        self.client.login(username="manager_dhaka", password="ManagerPassword123!")
        response = self.client.post("/dashboard/teller/deposit/", {
            "account_number": "AC60001",
            "amount": "1000.00",
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_unauthenticated_user_redirected(self):
        response = self.client.post("/dashboard/teller/deposit/", {
            "account_number": "AC60001",
            "amount": "1000.00",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_get_method_returns_method_not_allowed(self):
        self.client.login(username="teller_dhaka", password="TellerPassword123!")
        response = self.client.get("/dashboard/teller/deposit/")
        self.assertEqual(response.status_code, 405)


# =============================================================================
# Phase 2 — Teller Cash Withdrawal Integration Tests
# =============================================================================

class TellerWithdrawDashboardTest(TestCase):
    """
    Tests for Teller Cash Withdrawal endpoint (/dashboard/teller/withdraw/).

    Verifies:
    - Valid withdrawal creates PENDING transaction and leaves balances unchanged.
    - Insufficient balance rejects withdrawal attempt.
    - Withdrawal cannot be made for an account in a different branch.
    - Invalid amounts (negative, zero, NaN/Infinity, excessive precision) and non-existent accounts fail cleanly.
    - Non-Teller roles (Manager, Auditor) are denied with HTTP 403.
    - Unauthenticated requests redirect to /login/.
    - GET method returns 405 Method Not Allowed.
    - CSRF protection is enforced.
    - Audit log entry is created on successful withdrawal request.
    """

    def setUp(self):
        self.branch_a = Branch.objects.create(
            branch_code="BR701",
            branch_name="Motijheel Branch",
            district="Dhaka",
            address="Motijheel C/A",
            is_active=True,
        )
        self.branch_b = Branch.objects.create(
            branch_code="BR702",
            branch_name="Agrabad Branch",
            district="Chittagong",
            address="Agrabad C/A",
            is_active=True,
        )

        self.teller_group, _ = Group.objects.get_or_create(name="Teller")
        self.manager_group, _ = Group.objects.get_or_create(name="Manager")

        # Teller in Branch A
        self.teller_user = User.objects.create_user(
            username="teller_w_dhaka",
            password="TellerPassword123!",
            first_name="Tariq",
            last_name="Islam",
        )
        self.teller_user.groups.add(self.teller_group)
        StaffProfile.objects.create(
            user=self.teller_user,
            employee_id="EMP_TEL_W_DHAKA",
            branch=self.branch_a,
            designation="Cash Teller",
            is_active=True,
        )

        # Manager in Branch A
        self.manager_user = User.objects.create_user(
            username="manager_w_dhaka",
            password="ManagerPassword123!",
        )
        self.manager_user.groups.add(self.manager_group)
        StaffProfile.objects.create(
            user=self.manager_user,
            employee_id="EMP_MGR_W_DHAKA",
            branch=self.branch_a,
            designation="Branch Manager",
            is_active=True,
        )

        # Account Product
        self.product = AccountProduct.objects.create(
            product_code="SAV700",
            product_name="Savings Account",
            product_type=AccountProduct.ProductType.SAVINGS,
            minimum_balance=Decimal("500.00"),
            currency="BDT",
        )

        # Customer & Account in Branch A (Available Balance: 5000.00)
        self.customer_a = Customer.objects.create(
            full_name="Dhaka Customer",
            phone="01700000701",
            nid_number="NID7001",
            present_address="Dhaka",
            district="Dhaka",
            home_branch=self.branch_a,
            created_by=self.teller_user,
        )
        self.account_a = Account.objects.create(
            customer=self.customer_a,
            product=self.product,
            branch=self.branch_a,
            account_number="AC70001",
            available_balance=Decimal("5000.00"),
            ledger_balance=Decimal("5000.00"),
        )

        # Customer & Account in Branch B
        self.customer_b = Customer.objects.create(
            full_name="Chittagong Customer",
            phone="01700000702",
            nid_number="NID7002",
            present_address="Chittagong",
            district="Chittagong",
            home_branch=self.branch_b,
            created_by=self.teller_user,
        )
        self.account_b = Account.objects.create(
            customer=self.customer_b,
            product=self.product,
            branch=self.branch_b,
            account_number="AC70002",
            available_balance=Decimal("10000.00"),
            ledger_balance=Decimal("10000.00"),
        )

    def test_teller_can_create_withdrawal_successfully(self):
        self.client.login(username="teller_w_dhaka", password="TellerPassword123!")
        response = self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "1500.50",
            "description": "Counter Cash Withdrawal",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/teller/")

        # Verify transaction created in DB
        txn = Transaction.objects.get(account=self.account_a)
        self.assertEqual(txn.amount, Decimal("1500.50"))
        self.assertEqual(txn.transaction_type, Transaction.TransactionType.WITHDRAWAL)
        self.assertEqual(txn.authorization_status, Transaction.AuthorizationStatus.PENDING)
        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.created_by, self.teller_user)

    def test_withdrawal_leaves_balances_unchanged_before_approval(self):
        self.client.login(username="teller_w_dhaka", password="TellerPassword123!")
        self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "2000.00",
            "description": "Preapproval balance test",
        })
        self.account_a.refresh_from_db()
        # Balance must remain 5000.00 until Manager approval
        self.assertEqual(self.account_a.available_balance, Decimal("5000.00"))
        self.assertEqual(self.account_a.ledger_balance, Decimal("5000.00"))

    def test_withdrawal_creation_records_audit_log(self):
        self.client.login(username="teller_w_dhaka", password="TellerPassword123!")
        self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "1000.00",
            "description": "Audit log check",
        })
        txn = Transaction.objects.get(account=self.account_a)
        audit_exists = AuditLog.objects.filter(
            user=self.teller_user,
            action="CREATE_WITHDRAWAL",
            object_id=txn.transaction_id,
        ).exists()
        self.assertTrue(audit_exists)

    def test_teller_withdrawal_insufficient_balance_fails(self):
        self.client.login(username="teller_w_dhaka", password="TellerPassword123!")
        response = self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "10000.00",  # Available is 5000.00
            "description": "Excessive withdrawal",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.filter(account=self.account_a).count(), 0)

        # Balance remains unchanged
        self.account_a.refresh_from_db()
        self.assertEqual(self.account_a.available_balance, Decimal("5000.00"))

    def test_teller_cannot_withdraw_from_different_branch_account(self):
        self.client.login(username="teller_w_dhaka", password="TellerPassword123!")
        response = self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70002",  # Branch B account
            "amount": "1000.00",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.filter(account=self.account_b).count(), 0)

    def test_teller_withdrawal_invalid_inputs_fail(self):
        self.client.login(username="teller_w_dhaka", password="TellerPassword123!")

        # Non-existent account
        self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC99999",
            "amount": "1000.00",
        })
        # Negative amount
        self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "-500.00",
        })
        # Zero amount
        self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "0.00",
        })
        # Non-numeric format
        self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "abc_invalid",
        })
        # Excessive decimal precision (> 2 decimal places)
        self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "100.123",
        })
        # Non-finite amount
        self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "NaN",
        })

        self.assertEqual(Transaction.objects.count(), 0)

    def test_non_teller_denied_access_to_withdrawal_endpoint(self):
        self.client.login(username="manager_w_dhaka", password="ManagerPassword123!")
        response = self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "1000.00",
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_unauthenticated_user_redirected_on_withdraw(self):
        response = self.client.post("/dashboard/teller/withdraw/", {
            "account_number": "AC70001",
            "amount": "1000.00",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
        self.assertEqual(Transaction.objects.count(), 0)

    def test_get_method_returns_405_on_withdraw(self):
        self.client.login(username="teller_w_dhaka", password="TellerPassword123!")
        response = self.client.get("/dashboard/teller/withdraw/")
        self.assertEqual(response.status_code, 405)

    def test_withdraw_csrf_enforcement(self):
        from django.test import Client
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.login(username="teller_w_dhaka", password="TellerPassword123!")
        response = csrf_client.post(
            "/dashboard/teller/withdraw/",
            data="account_number=AC70001&amount=1000.00",
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 403)



