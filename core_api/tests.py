from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase

from accounts.models import Account
from branches.models import Branch
from customers.models import Customer
from products.models import AccountProduct
from transactions.models import Transaction
from users.models import StaffProfile


class ManagerPendingTransactionsApiTests(TestCase):
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

    def _create_transaction(self, account, *, authorization_status=None):
        fields = {
            "transaction_type": Transaction.TransactionType.DEPOSIT,
            "account": account,
            "amount": Decimal("123.45"),
            "created_by": self.teller,
        }
        if authorization_status is not None:
            fields["authorization_status"] = authorization_status
        return Transaction.objects.create(**fields)

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

# Create your tests here.
