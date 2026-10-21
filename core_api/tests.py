import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.db import DatabaseError, IntegrityError
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


class AdminCustomersApiTests(TestCase):
    endpoint = "/api/admin/customers/"

    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(username="customer_admin")
        self.admin.groups.add(self.admin_group)
        self.branch = Branch.objects.create(
            branch_code="CUST001",
            branch_name="Customer API Branch",
            district="Dhaka",
            address="Customer API branch address",
        )

    def _create_customer(self, name, *, district="Dhaka"):
        return Customer.objects.create(
            full_name=name,
            phone="01700000000",
            email="customer@example.com",
            nid_number=f"NID-{name}",
            passport_number=f"PASS-{name}",
            present_address="Sensitive present address",
            permanent_address="Sensitive permanent address",
            district=district,
            home_branch=self.branch,
            created_by=self.admin,
        )

    def _registration_payload(self):
        return {
            "customer_type": Customer.CustomerType.INDIVIDUAL,
            "full_name": "New API Customer",
            "phone": "01712345678",
            "email": "new.customer@example.com",
            "date_of_birth": "1990-05-15",
            "gender": Customer.Gender.OTHER,
            "nid_number": "NID-NEW-API-001",
            "passport_number": "",
            "present_address": "Test present address",
            "permanent_address": "",
            "district": "Dhaka",
            "home_branch": self.branch.pk,
            "nominee_name": "",
            "nominee_relationship": "",
            "nominee_phone": "",
        }

    def _post_registration(self, payload=None, *, client=None, raw_body=None):
        client = client or self.client
        body = json.dumps(payload) if raw_body is None else raw_body
        return client.post(
            self.endpoint,
            data=body,
            content_type="application/json",
        )

    def test_active_admin_receives_minimal_paginated_customer_list(self):
        customer = self._create_customer("Alice Customer")
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["pagination"], {
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
            "total_items": 1,
            "has_next": False,
            "has_previous": False,
        })
        self.assertEqual(data["customers"], [{
            "id": customer.pk,
            "full_name": "Alice Customer",
            "customer_type": Customer.CustomerType.INDIVIDUAL,
            "kyc_status": Customer.KYCStatus.PENDING,
            "status": Customer.Status.ACTIVE,
            "home_branch": "Customer API Branch",
            "created_at": customer.created_at.isoformat(),
        }])

    def test_admin_can_register_individual_and_receives_minimal_confirmation(self):
        self.client.force_login(self.admin)

        response = self._post_registration(self._registration_payload())

        self.assertEqual(response.status_code, 201)
        data = response.json()
        customer = Customer.objects.get(pk=data["customer"]["id"])
        self.assertEqual(data, {
            "success": True,
            "customer": {
                "id": customer.pk,
                "cif_number": customer.cif_number,
                "full_name": "New API Customer",
                "home_branch": "Customer API Branch",
                "kyc_status": Customer.KYCStatus.PENDING,
            },
        })
        self.assertEqual(customer.created_by, self.admin)
        self.assertEqual(customer.home_branch, self.branch)
        self.assertEqual(customer.status, Customer.Status.ACTIVE)
        self.assertEqual(customer.risk_level, Customer.RiskLevel.LOW)
        self.assertIsNone(customer.passport_number)
        self.assertNotIn("nid_number", data["customer"])
        self.assertNotIn("phone", data["customer"])
        self.assertNotIn("present_address", data["customer"])

    def test_admin_can_register_organization_without_personal_identity_document(self):
        payload = self._registration_payload()
        payload.update({
            "customer_type": Customer.CustomerType.ORGANIZATION,
            "full_name": "Example Organization",
            "nid_number": "",
            "passport_number": "",
            "date_of_birth": None,
            "gender": None,
        })
        self.client.force_login(self.admin)

        response = self._post_registration(payload)

        self.assertEqual(response.status_code, 201)
        customer = Customer.objects.get(pk=response.json()["customer"]["id"])
        self.assertEqual(customer.customer_type, Customer.CustomerType.ORGANIZATION)
        self.assertIsNone(customer.nid_number)
        self.assertIsNone(customer.passport_number)

    def test_individual_without_identity_document_is_rejected(self):
        payload = self._registration_payload()
        payload["nid_number"] = ""
        payload["passport_number"] = " "
        self.client.force_login(self.admin)

        response = self._post_registration(payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("nid_number", response.json()["errors"])
        self.assertEqual(Customer.objects.count(), 0)

    def test_missing_non_identity_required_fields_are_rejected(self):
        payload = self._registration_payload()
        payload.pop("present_address")
        self.client.force_login(self.admin)

        response = self._post_registration(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"]["present_address"], [
            "This field is required.",
        ])
        self.assertEqual(Customer.objects.count(), 0)

    def test_nonexistent_and_inactive_branches_are_rejected(self):
        inactive_branch = Branch.objects.create(
            branch_code="CUST002",
            branch_name="Inactive Customer Branch",
            district="Dhaka",
            address="Inactive branch address",
            is_active=False,
        )
        self.client.force_login(self.admin)

        for branch_id in (99999, inactive_branch.pk):
            with self.subTest(branch_id=branch_id):
                payload = self._registration_payload()
                payload["home_branch"] = branch_id
                response = self._post_registration(payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn("home_branch", response.json()["errors"])
        self.assertEqual(Customer.objects.count(), 0)

    def test_malformed_and_non_object_json_are_rejected(self):
        self.client.force_login(self.admin)

        malformed_response = self._post_registration(raw_body="{")
        array_response = self._post_registration(raw_body="[]")

        self.assertEqual(malformed_response.status_code, 400)
        self.assertEqual(array_response.status_code, 400)
        self.assertEqual(Customer.objects.count(), 0)

    def test_unknown_fields_and_privileged_fields_are_rejected(self):
        self.client.force_login(self.admin)
        privileged_fields = (
            "created_by",
            "cif_number",
            "kyc_status",
            "risk_level",
            "status",
            "created_at",
            "updated_at",
        )

        for field in privileged_fields:
            with self.subTest(field=field):
                payload = self._registration_payload()
                payload[field] = "client-supplied"
                response = self._post_registration(payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Customer.objects.count(), 0)

        payload = self._registration_payload()
        payload["unsupported"] = "value"
        response = self._post_registration(payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Customer.objects.count(), 0)

    def test_invalid_types_choices_dates_and_oversized_inputs_are_rejected(self):
        invalid_payloads = []
        payload = self._registration_payload()
        payload["full_name"] = 123
        invalid_payloads.append(("wrong_type", payload))

        payload = self._registration_payload()
        payload["customer_type"] = "UNKNOWN"
        invalid_payloads.append(("invalid_customer_type", payload))

        payload = self._registration_payload()
        payload["gender"] = "UNKNOWN"
        invalid_payloads.append(("invalid_gender", payload))

        payload = self._registration_payload()
        payload["date_of_birth"] = "2026-02-30"
        invalid_payloads.append(("invalid_date", payload))

        payload = self._registration_payload()
        payload["date_of_birth"] = "2999-01-01"
        invalid_payloads.append(("future_date", payload))

        payload = self._registration_payload()
        payload["date_of_birth"] = "19900515"
        invalid_payloads.append(("noncanonical_date", payload))

        payload = self._registration_payload()
        payload["full_name"] = "x" * 151
        invalid_payloads.append(("oversized_field", payload))

        self.client.force_login(self.admin)
        for case, payload in invalid_payloads:
            with self.subTest(case=case):
                response = self._post_registration(payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(Customer.objects.count(), 0)

        oversized_body = json.dumps({
            **self._registration_payload(),
            "present_address": "x" * 17000,
        })
        response = self._post_registration(raw_body=oversized_body)
        self.assertEqual(response.status_code, 413)
        self.assertEqual(Customer.objects.count(), 0)

    def test_duplicate_nid_and_passport_are_rejected_without_leaking_values(self):
        existing = self._create_customer("Existing Identity")
        self.client.force_login(self.admin)

        for field, value in (
            ("nid_number", existing.nid_number),
            ("passport_number", existing.passport_number),
        ):
            with self.subTest(field=field):
                payload = self._registration_payload()
                payload[field] = value
                response = self._post_registration(payload)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(value, response.content.decode())
        self.assertEqual(Customer.objects.count(), 1)

    def test_audit_entry_is_created_with_request_user_and_safe_description(self):
        payload = self._registration_payload()
        payload["passport_number"] = "PASS-PRIVATE-001"
        self.client.force_login(self.admin)

        response = self._post_registration(payload)

        self.assertEqual(response.status_code, 201)
        customer = Customer.objects.get(pk=response.json()["customer"]["id"])
        audit = AuditLog.objects.get(
            action="CREATE_CUSTOMER",
            model_name="Customer",
            object_id=str(customer.pk),
        )
        self.assertEqual(audit.user, self.admin)
        self.assertNotIn(payload["nid_number"], audit.description)
        self.assertNotIn(payload["passport_number"], audit.description)

    def test_audit_failure_rolls_back_customer_creation(self):
        self.client.force_login(self.admin)
        initial_count = Customer.objects.count()

        with patch.object(
            AuditLog.objects,
            "create",
            side_effect=DatabaseError("simulated audit database failure"),
        ):
            response = self._post_registration(self._registration_payload())

        self.assertEqual(response.status_code, 500)
        self.assertEqual(Customer.objects.count(), initial_count)
        self.assertNotIn(
            "NID-NEW-API-001",
            response.content.decode(),
        )

    def test_integrity_error_is_handled_without_exposing_database_details(self):
        self.client.force_login(self.admin)

        with patch(
            "core_api.views.Customer.save",
            side_effect=IntegrityError("sensitive database detail"),
        ):
            response = self._post_registration(self._registration_payload())

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json()["message"],
            "Customer registration conflicts with an existing record.",
        )
        self.assertNotIn("sensitive database detail", response.content.decode())

    def test_csrf_is_required_for_customer_registration(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        client.get("/api/csrf/")

        missing_token_response = self._post_registration(
            self._registration_payload(),
            client=client,
        )
        self.assertEqual(missing_token_response.status_code, 403)
        self.assertEqual(Customer.objects.count(), 0)

        csrf_token = client.cookies["csrftoken"].value
        valid_response = client.post(
            self.endpoint,
            data=json.dumps(self._registration_payload()),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(valid_response.status_code, 201)

    def test_non_admins_cannot_register_customers(self):
        manager = User.objects.create_user(username="registration_manager")
        manager.groups.add(Group.objects.get_or_create(name="Manager")[0])
        teller = User.objects.create_user(username="registration_teller")
        teller.groups.add(Group.objects.get_or_create(name="Teller")[0])
        superuser = User.objects.create_superuser(
            username="registration_superuser",
            email="registration-superuser@example.com",
            password="test-password",
        )
        conflicting_admin = User.objects.create_user(
            username="conflicting_registration_admin",
        )
        conflicting_admin.groups.add(
            self.admin_group,
            Group.objects.get_or_create(name="Manager")[0],
        )
        inactive_admin = User.objects.create_user(username="inactive_registration_admin")
        inactive_admin.groups.add(self.admin_group)
        inactive_admin.is_active = False
        inactive_admin.save(update_fields=["is_active"])

        denied_users = (
            ("anonymous", None, 401),
            ("manager", manager, 403),
            ("teller", teller, 403),
            ("ungrouped_superuser", superuser, 403),
            ("conflicting_admin", conflicting_admin, 403),
            ("inactive_admin", inactive_admin, 401),
        )
        for label, user, expected_status in denied_users:
            with self.subTest(user=label):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                response = self._post_registration(self._registration_payload())
                self.assertEqual(response.status_code, expected_status)
        self.assertEqual(Customer.objects.count(), 0)

    def test_search_is_case_insensitive_and_matches_customer_fields(self):
        matching_customer = self._create_customer("Marie Searchable")
        self._create_customer("Another Customer", district="Search District")
        self._create_customer("Unrelated Customer")
        self.client.force_login(self.admin)

        name_response = self.client.get(self.endpoint, {"search": "mArIe"})
        district_response = self.client.get(
            self.endpoint,
            {"search": "sEaRcH dIsTrIcT"},
        )

        self.assertEqual(name_response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in name_response.json()["customers"]],
            [matching_customer.pk],
        )
        self.assertEqual(district_response.status_code, 200)
        self.assertEqual(
            len(district_response.json()["customers"]),
            1,
        )
        self.assertEqual(district_response.json()["pagination"]["total_items"], 1)

    def test_customer_results_are_paginated_with_stable_ordering(self):
        customers = [
            self._create_customer(f"Customer {index:02d}")
            for index in range(12)
        ]
        self.client.force_login(self.admin)

        first_page = self.client.get(self.endpoint)
        second_page = self.client.get(self.endpoint, {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        first_data = first_page.json()
        second_data = second_page.json()
        first_ids = [item["id"] for item in first_data["customers"]]
        second_ids = [item["id"] for item in second_data["customers"]]
        self.assertEqual(len(first_ids), 10)
        self.assertEqual(len(second_ids), 2)
        self.assertFalse(set(first_ids) & set(second_ids))
        self.assertEqual(
            first_ids + second_ids,
            [customer.pk for customer in reversed(customers)],
        )
        self.assertEqual(second_data["pagination"]["page"], 2)

    def test_anonymous_user_is_denied(self):
        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_inactive_admin_is_denied(self):
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def test_manager_is_denied(self):
        manager = User.objects.create_user(username="customer_manager")
        manager.groups.add(Group.objects.get_or_create(name="Manager")[0])
        self.client.force_login(manager)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_teller_is_denied(self):
        teller = User.objects.create_user(username="customer_teller")
        teller.groups.add(Group.objects.get_or_create(name="Teller")[0])
        self.client.force_login(teller)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_ungrouped_superuser_is_denied(self):
        superuser = User.objects.create_superuser(
            username="customer_superuser",
            email="customer-superuser@example.com",
            password="test-password",
        )
        self.client.force_login(superuser)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_admin_with_manager_membership_is_denied(self):
        self.admin.groups.add(Group.objects.get_or_create(name="Manager")[0])
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["success"])

    def test_sensitive_identifiers_and_contact_data_are_not_returned(self):
        self._create_customer("Private Customer")
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        customer_data = response.json()["customers"][0]
        for field in (
            "nid_number",
            "passport_number",
            "phone",
            "email",
            "date_of_birth",
            "present_address",
            "permanent_address",
            "nominee_name",
            "nominee_phone",
        ):
            self.assertNotIn(field, customer_data)
        self.assertIn("id", customer_data)

    def test_invalid_pages_are_safely_normalized(self):
        customers = [
            self._create_customer(f"Page Customer {index}")
            for index in range(11)
        ]
        self.client.force_login(self.admin)

        for page in ("not-a-number", "-1", "0"):
            with self.subTest(page=page):
                response = self.client.get(self.endpoint, {"page": page})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["pagination"]["page"], 1)

        last_page = self.client.get(self.endpoint, {"page": "999"})
        self.assertEqual(last_page.status_code, 200)
        self.assertEqual(last_page.json()["pagination"]["page"], 2)
        self.assertEqual(len(last_page.json()["customers"]), 1)
        self.assertEqual(last_page.json()["pagination"]["total_items"], len(customers))

    def test_overlong_search_returns_json_validation_error(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint, {"search": "x" * 101})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {
            "success": False,
            "message": "Search query must be 100 characters or fewer.",
        })

    def test_endpoint_rejects_non_get_methods(self):
        self.client.force_login(self.admin)

        response = self.client.put(self.endpoint)

        self.assertEqual(response.status_code, 405)


class AdminBranchOptionsApiTests(TestCase):
    endpoint = "/api/admin/branches/options/"

    def setUp(self):
        self.admin_group, _ = Group.objects.get_or_create(name="Admin")
        self.admin = User.objects.create_user(username="branch_options_admin")
        self.admin.groups.add(self.admin_group)
        self.branch_b = Branch.objects.create(
            branch_code="BR002",
            branch_name="Branch B",
            district="Dhaka",
            address="Branch B address",
        )
        self.branch_a = Branch.objects.create(
            branch_code="BR001",
            branch_name="Branch A",
            district="Dhaka",
            address="Branch A address",
        )
        self.inactive_branch = Branch.objects.create(
            branch_code="BR003",
            branch_name="Inactive Branch",
            district="Dhaka",
            address="Inactive branch address",
            is_active=False,
        )

    def test_active_admin_receives_only_active_branch_option_fields(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "success": True,
            "branches": [
                {
                    "id": self.branch_a.pk,
                    "branch_code": "BR001",
                    "branch_name": "Branch A",
                },
                {
                    "id": self.branch_b.pk,
                    "branch_code": "BR002",
                    "branch_name": "Branch B",
                },
            ],
        })
        self.assertNotIn("address", response.content.decode())
        self.assertNotIn("is_active", response.content.decode())

    def test_branch_options_require_authorized_active_admin(self):
        manager = User.objects.create_user(username="branch_options_manager")
        manager.groups.add(Group.objects.get_or_create(name="Manager")[0])
        teller = User.objects.create_user(username="branch_options_teller")
        teller.groups.add(Group.objects.get_or_create(name="Teller")[0])
        ungrouped_superuser = User.objects.create_superuser(
            username="branch_options_superuser",
            email="branch-options-superuser@example.com",
            password="test-password",
        )
        inactive_admin = User.objects.create_user(
            username="inactive_branch_options_admin",
            is_active=False,
        )
        inactive_admin.groups.add(self.admin_group)
        conflicting_admin = User.objects.create_user(
            username="conflicting_branch_options_admin",
        )
        conflicting_admin.groups.add(
            self.admin_group,
            Group.objects.get_or_create(name="Manager")[0],
        )

        denied_users = (
            ("anonymous", None, 401),
            ("manager", manager, 403),
            ("teller", teller, 403),
            ("ungrouped_superuser", ungrouped_superuser, 403),
            ("inactive_admin", inactive_admin, 401),
            ("conflicting_admin", conflicting_admin, 403),
        )
        for label, user, expected_status in denied_users:
            with self.subTest(user=label):
                self.client.logout()
                if user:
                    self.client.force_login(user)
                response = self.client.get(self.endpoint)
                self.assertEqual(response.status_code, expected_status)


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
