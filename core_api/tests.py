from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase

from accounts.models import Account
from audit.models import AuditLog
from branches.models import Branch
from customers.models import Customer
from products.models import AccountProduct
from transactions.models import Transaction, TransactionEntry
from users.models import StaffProfile


class ManagerApiTestCase(TestCase):
    endpoint = "/api/manager/pending-transactions/"

    def setUp(self):
        self.branch_a = Branch.objects.create(
            branch_code="API001",
            branch_name="API Branch A",
            district="Dhaka",
            address="Branch A address",
        )
        self.branch_b = Branch.objects.create(
            branch_code="API002",
            branch_name="API Branch B",
            district="Chattogram",
            address="Branch B address",
        )
        self.manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.manager = User.objects.create_user(username="api_manager", password="test-pass")
        self.manager.groups.add(self.manager_group)
        StaffProfile.objects.create(
            user=self.manager,
            employee_id="API-MGR-001",
            branch=self.branch_a,
        )
        self.teller = User.objects.create_user(username="api_teller", password="test-pass")
        Group.objects.get_or_create(name="Teller")
        self.teller.groups.add(Group.objects.get(name="Teller"))

        self.product = AccountProduct.objects.create(
            product_code="API-SAV",
            product_name="API Savings",
            minimum_balance=Decimal("0.00"),
        )
        self.account_a = self._create_account(self.branch_a, "API-ACC-A")
        self.account_b = self._create_account(self.branch_b, "API-ACC-B")

    def _create_account(self, branch, account_number):
        customer = Customer.objects.create(
            full_name=f"Customer {account_number}",
            phone="01700000000",
            nid_number=f"NID-{account_number}",
            present_address="Test address",
            district=branch.district,
            home_branch=branch,
            created_by=self.teller,
        )
        return Account.objects.create(
            customer=customer,
            product=self.product,
            branch=branch,
            account_number=account_number,
        )

    def _create_transaction(
        self,
        account,
        *,
        authorization_status=None,
        created_by=None,
        transaction_type=Transaction.TransactionType.DEPOSIT,
        status=Transaction.Status.PENDING,
    ):
        fields = {
            "transaction_type": transaction_type,
            "account": account,
            "amount": Decimal("123.45"),
            "created_by": created_by or self.teller,
            "status": status,
        }
        if authorization_status is not None:
            fields["authorization_status"] = authorization_status
        return Transaction.objects.create(**fields)

    def _create_postable_transaction(self, account, *, created_by=None):
        transaction = self._create_transaction(account, created_by=created_by)
        for entry_type in (
            TransactionEntry.EntryType.DEBIT,
            TransactionEntry.EntryType.CREDIT,
        ):
            TransactionEntry.objects.create(
                transaction=transaction,
                account=account,
                entry_type=entry_type,
                amount=transaction.amount,
            )
        return transaction


class AdminSessionApiTests(TestCase):
    endpoint = "/api/admin/session/"

    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(username="api_admin")
        self.admin.groups.add(self.admin_group)

    def test_anonymous_user_is_denied(self):
        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_inactive_user_is_denied(self):
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_manager_is_denied(self):
        manager = User.objects.create_user(username="api_manager")
        manager.groups.add(Group.objects.get(name="Manager"))
        self.client.force_login(manager)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_teller_is_denied(self):
        teller = User.objects.create_user(username="api_teller")
        teller_group, _ = Group.objects.get_or_create(name="Teller")
        teller.groups.add(teller_group)
        self.client.force_login(teller)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_active_admin_group_member_is_allowed(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "success": True,
            "username": "api_admin",
            "role": "Admin",
        })

    def test_ungrouped_superuser_is_denied(self):
        superuser = User.objects.create_superuser(
            username="api_superuser",
            email="superuser@example.com",
            password="local-test-password",
        )
        self.client.force_login(superuser)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_admin_with_manager_membership_is_denied(self):
        manager_group, _ = Group.objects.get_or_create(name="Manager")
        self.admin.groups.add(manager_group)
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])


class ManagerPendingTransactionsApiTests(ManagerApiTestCase):
    def test_authenticated_manager_receives_pending_transactions(self):
        transaction = self._create_transaction(self.account_a)
        self.client.force_login(self.manager)

        response = self.client.get(self.endpoint, {"account_number": "API-ACC"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pending_count"], 1)
        self.assertEqual(len(data["transactions"]), 1)
        self.assertEqual(
            data["transactions"][0],
            {
                "id": transaction.pk,
                "transaction_id": transaction.transaction_id,
                "transaction_type": Transaction.TransactionType.DEPOSIT,
                "account_number": self.account_a.account_number,
                "amount": "123.45",
                "status": Transaction.Status.PENDING,
                "authorization_status": Transaction.AuthorizationStatus.PENDING,
                "created_by": self.teller.username,
                "created_at": transaction.created_at.isoformat(),
            },
        )
        self.assertEqual(data["pagination"]["page_size"], 10)

    def test_unauthenticated_request_returns_401(self):
        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 401)

    def test_non_manager_request_returns_403(self):
        self.client.force_login(self.teller)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)

    def test_manager_sees_only_pending_transactions_in_assigned_branch(self):
        own_transaction = self._create_transaction(self.account_a)
        self._create_transaction(self.account_b)
        self._create_transaction(
            self.account_a,
            authorization_status=Transaction.AuthorizationStatus.APPROVED,
        )
        self.client.force_login(self.manager)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pending_count"], 1)
        self.assertEqual(
            response.json()["transactions"][0]["transaction_id"],
            own_transaction.transaction_id,
        )

    def test_results_are_paginated_in_pages_of_ten(self):
        for _ in range(11):
            self._create_transaction(self.account_a)
        self.client.force_login(self.manager)

        first_page = self.client.get(self.endpoint)
        second_page = self.client.get(self.endpoint, {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.json()["pending_count"], 11)
        self.assertEqual(len(first_page.json()["transactions"]), 10)
        self.assertTrue(first_page.json()["pagination"]["has_next"])
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.json()["transactions"]), 1)
        self.assertEqual(second_page.json()["pagination"]["page"], 2)
        self.assertFalse(second_page.json()["pagination"]["has_next"])

    def test_manager_without_branch_gets_empty_results(self):
        branchless_manager = User.objects.create_user(
            username="branchless_manager",
            password="test-pass",
        )
        branchless_manager.groups.add(self.manager_group)
        self._create_transaction(self.account_a)
        self.client.force_login(branchless_manager)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pending_count"], 0)
        self.assertEqual(response.json()["transactions"], [])

    def test_superuser_with_manager_role_and_no_branch_sees_all_pending(self):
        superuser_manager = User.objects.create_superuser(
            username="global_manager",
            email="global-manager@example.com",
            password="test-pass",
        )
        superuser_manager.groups.add(self.manager_group)
        self._create_transaction(self.account_a)
        self._create_transaction(self.account_b)
        self.client.force_login(superuser_manager)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pending_count"], 2)

    def test_endpoint_rejects_non_get_methods(self):
        response = self.client.post(self.endpoint)

        self.assertEqual(response.status_code, 405)


class TellerApiTests(ManagerApiTestCase):
    session_endpoint = "/api/teller/session/"
    transactions_endpoint = "/api/teller/transactions/"

    def setUp(self):
        super().setUp()
        StaffProfile.objects.create(
            user=self.teller,
            employee_id="API-TEL-001",
            branch=self.branch_a,
        )

    def test_teller_session_returns_minimal_identity_and_branch(self):
        self.client.force_login(self.teller)

        response = self.client.get(self.session_endpoint)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "success": True,
            "username": self.teller.username,
            "role": "Teller",
            "branch": self.branch_a.branch_name,
        })

    def test_teller_session_requires_authentication_and_role(self):
        response = self.client.get(self.session_endpoint)
        self.assertEqual(response.status_code, 401)

        self.client.force_login(self.manager)
        response = self.client.get(self.session_endpoint)
        self.assertEqual(response.status_code, 403)

    def test_teller_history_is_scoped_and_exposes_only_required_fields(self):
        own_transaction = self._create_transaction(self.account_a)
        self._create_transaction(self.account_a, created_by=self.manager)
        self.client.force_login(self.teller)

        response = self.client.get(self.transactions_endpoint)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pagination"]["total_items"], 1)
        self.assertEqual(len(data["transactions"]), 1)
        self.assertEqual(data["transactions"][0], {
            "id": own_transaction.pk,
            "transaction_id": own_transaction.transaction_id,
            "transaction_type": Transaction.TransactionType.DEPOSIT,
            "account_number": self.account_a.account_number,
            "amount": "123.45",
            "status": Transaction.Status.PENDING,
            "authorization_status": Transaction.AuthorizationStatus.PENDING,
            "created_at": own_transaction.created_at.isoformat(),
        })

    def test_teller_history_supports_existing_filters(self):
        matching_transaction = self._create_transaction(
            self.account_a,
            transaction_type=Transaction.TransactionType.DEPOSIT,
            status=Transaction.Status.PENDING,
        )
        self._create_transaction(
            self.account_b,
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.REJECTED,
        )
        self.client.force_login(self.teller)

        response = self.client.get(self.transactions_endpoint, {
            "account_number": self.account_a.account_number,
            "transaction_type": Transaction.TransactionType.DEPOSIT,
            "status": Transaction.Status.PENDING,
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["transactions"]],
            [matching_transaction.pk],
        )

    def test_teller_history_is_paginated_in_pages_of_ten(self):
        for _ in range(11):
            self._create_transaction(self.account_a)
        self.client.force_login(self.teller)

        first_page = self.client.get(self.transactions_endpoint)
        second_page = self.client.get(self.transactions_endpoint, {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.json()["pagination"]["total_items"], 11)
        self.assertEqual(len(first_page.json()["transactions"]), 10)
        self.assertTrue(first_page.json()["pagination"]["has_next"])
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.json()["transactions"]), 1)
        self.assertEqual(second_page.json()["pagination"]["page"], 2)

    def test_teller_history_requires_authentication_and_role(self):
        response = self.client.get(self.transactions_endpoint)
        self.assertEqual(response.status_code, 401)

        self.client.force_login(self.manager)
        response = self.client.get(self.transactions_endpoint)
        self.assertEqual(response.status_code, 403)


class ManagerTransactionActionApiTests(ManagerApiTestCase):
    def _action_url(self, transaction_id, action):
        return f"/api/manager/transactions/{transaction_id}/{action}/"

    def test_action_endpoints_only_accept_post(self):
        transaction = self._create_transaction(self.account_a)

        for action in ("approve", "reject"):
            with self.subTest(action=action):
                response = self.client.get(self._action_url(transaction.pk, action))
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.json()["success"], False)

    def test_action_endpoints_require_authentication(self):
        transaction = self._create_transaction(self.account_a)

        for action in ("approve", "reject"):
            with self.subTest(action=action):
                response = self.client.post(
                    self._action_url(transaction.pk, action),
                    data={},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["success"], False)

    def test_action_endpoints_reject_non_managers(self):
        transaction = self._create_transaction(self.account_a)
        self.client.force_login(self.teller)

        for action in ("approve", "reject"):
            with self.subTest(action=action):
                response = self.client.post(
                    self._action_url(transaction.pk, action),
                    data={},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 403)

    def test_manager_cannot_act_on_transactions_outside_their_branch(self):
        transaction = self._create_transaction(self.account_b)
        self.client.force_login(self.manager)

        for action in ("approve", "reject"):
            with self.subTest(action=action):
                response = self.client.post(
                    self._action_url(transaction.pk, action),
                    data={},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 403)
                transaction.refresh_from_db()
                self.assertEqual(
                    transaction.authorization_status,
                    Transaction.AuthorizationStatus.PENDING,
                )

    def test_maker_cannot_approve_or_reject_own_transaction(self):
        transaction = self._create_transaction(
            self.account_a,
            created_by=self.manager,
        )
        self.client.force_login(self.manager)

        for action in ("approve", "reject"):
            with self.subTest(action=action):
                response = self.client.post(
                    self._action_url(transaction.pk, action),
                    data={"reason": "Not applicable"},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("created", response.json()["message"])
                transaction.refresh_from_db()
                self.assertEqual(
                    transaction.authorization_status,
                    Transaction.AuthorizationStatus.PENDING,
                )

    def test_unknown_primary_key_returns_json_404(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            self._action_url(99999999, "approve"),
            data={},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["message"], "Transaction not found.")

    def test_non_pending_transaction_cannot_be_processed(self):
        self.client.force_login(self.manager)

        for action in ("approve", "reject"):
            transaction = self._create_transaction(
                self.account_a,
                authorization_status=Transaction.AuthorizationStatus.APPROVED,
            )
            with self.subTest(action=action):
                response = self.client.post(
                    self._action_url(transaction.pk, action),
                    data={},
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["message"],
                    "Only pending transactions can be processed.",
                )
                transaction.refresh_from_db()
                self.assertEqual(
                    transaction.authorization_status,
                    Transaction.AuthorizationStatus.APPROVED,
                )

    def test_csrf_is_required_for_both_action_endpoints(self):
        transaction = self._create_transaction(self.account_a)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)

        for action in ("approve", "reject"):
            with self.subTest(action=action):
                response = client.post(
                    self._action_url(transaction.pk, action),
                    data={},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {
                    "success": False,
                    "message": "CSRF verification failed.",
                })
                transaction.refresh_from_db()
                self.assertEqual(
                    transaction.authorization_status,
                    Transaction.AuthorizationStatus.PENDING,
                )

    def test_reject_validates_optional_reason(self):
        transaction = self._create_transaction(self.account_a)
        self.client.force_login(self.manager)

        for reason in (123, "x" * 501):
            with self.subTest(reason_type=type(reason).__name__, length=len(str(reason))):
                response = self.client.post(
                    self._action_url(transaction.pk, "reject"),
                    data={"reason": reason},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)

        transaction.refresh_from_db()
        self.assertEqual(
            transaction.authorization_status,
            Transaction.AuthorizationStatus.PENDING,
        )

    def test_manager_can_approve_and_post_transaction(self):
        transaction = self._create_postable_transaction(self.account_a)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        client.get("/api/csrf/")
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            self._action_url(transaction.pk, "approve"),
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "success": True,
            "message": "Transaction approved successfully.",
        })
        transaction.refresh_from_db()
        self.account_a.refresh_from_db()
        self.assertEqual(
            transaction.authorization_status,
            Transaction.AuthorizationStatus.APPROVED,
        )
        self.assertEqual(transaction.status, Transaction.Status.POSTED)
        self.assertEqual(transaction.approved_by, self.manager)
        self.assertEqual(self.account_a.available_balance, Decimal("123.45"))
        self.assertEqual(self.account_a.ledger_balance, Decimal("123.45"))
        self.assertTrue(
            AuditLog.objects.filter(
                action="APPROVE_TRANSACTION",
                object_id=transaction.transaction_id,
                user=self.manager,
            ).exists()
        )

    def test_manager_can_reject_without_changing_balance(self):
        transaction = self._create_transaction(self.account_a)
        self.client.force_login(self.manager)

        response = self.client.post(
            self._action_url(transaction.pk, "reject"),
            data={"reason": "Needs additional review"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        transaction.refresh_from_db()
        self.account_a.refresh_from_db()
        self.assertEqual(
            transaction.authorization_status,
            Transaction.AuthorizationStatus.REJECTED,
        )
        self.assertEqual(transaction.status, Transaction.Status.REJECTED)
        self.assertEqual(transaction.rejection_reason, "Needs additional review")
        self.assertEqual(self.account_a.available_balance, Decimal("0.00"))
        self.assertEqual(self.account_a.ledger_balance, Decimal("0.00"))
        self.assertTrue(
            AuditLog.objects.filter(
                action="REJECT_TRANSACTION",
                object_id=transaction.transaction_id,
                user=self.manager,
                description__contains="Needs additional review",
            ).exists()
        )


# Create your tests here.
