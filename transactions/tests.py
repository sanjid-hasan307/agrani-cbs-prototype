from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User, Group
from rest_framework.test import APIClient
from rest_framework import status
from branches.models import Branch
from users.models import StaffProfile
from customers.models import Customer
from products.models import AccountProduct
from accounts.models import Account
from audit.models import AuditLog
from transactions.models import Transaction, TransactionEntry
from transactions.services.deposit_service import deposit
from transactions.services.withdrawal_service import withdraw
from transactions.services.transfer_service import transfer
from transactions.services.authorization_service import approve_transaction, reject_transaction
from transactions.services.posting_service import post_transaction


class TransactionModelTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
            is_active=True,
        )
        self.user = User.objects.create_user(username="teller1", password="Password123!")
        self.customer = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Rahim Uddin",
            date_of_birth=date(1985, 3, 20),
            nid_number="1985123456789",
            phone="01811111111",
            present_address="45 Gulshan, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.user,
            status=Customer.Status.ACTIVE,
        )
        self.product = AccountProduct.objects.get(product_code="SAV")
        self.account = Account.objects.create(
            customer=self.customer,
            product=self.product,
            branch=self.branch,
        )
        self.transaction_data = {
            "transaction_type": Transaction.TransactionType.DEPOSIT,
            "account": self.account,
            "amount": Decimal("5000.00"),
            "created_by": self.user,
        }

    def test_transaction_creation(self):
        txn = Transaction.objects.create(**self.transaction_data)
        self.assertTrue(txn.transaction_id.startswith("TXN"))
        self.assertEqual(txn.transaction_type, Transaction.TransactionType.DEPOSIT)
        self.assertEqual(txn.account, self.account)
        self.assertEqual(txn.amount, Decimal("5000.00"))
        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.authorization_status, Transaction.AuthorizationStatus.PENDING)
        self.assertEqual(txn.created_by, self.user)
        self.assertIsNone(txn.authorized_by)
        self.assertIsNone(txn.approved_by)
        self.assertIsNone(txn.approved_at)
        self.assertIsNotNone(txn.created_at)

    def test_transaction_id_generation(self):
        txn1 = Transaction.objects.create(**self.transaction_data)
        txn2 = Transaction.objects.create(**self.transaction_data)

        self.assertRegex(txn1.transaction_id, r'^TXN\d{8}$')
        self.assertRegex(txn2.transaction_id, r'^TXN\d{8}$')
        self.assertLess(int(txn1.transaction_id[3:]), int(txn2.transaction_id[3:]))

    def test_unique_transaction_id(self):
        txn1 = Transaction.objects.create(**self.transaction_data)
        txn2 = Transaction.objects.create(**self.transaction_data)
        self.assertNotEqual(txn1.transaction_id, txn2.transaction_id)

    def test_positive_amount_validation(self):
        invalid_data = self.transaction_data.copy()
        invalid_data["amount"] = Decimal("0.00")
        txn = Transaction(**invalid_data)
        with self.assertRaises(ValidationError) as ctx:
            txn.save()
        self.assertIn("amount", ctx.exception.message_dict)

        invalid_data["amount"] = Decimal("-100.00")
        txn2 = Transaction(**invalid_data)
        with self.assertRaises(ValidationError) as ctx2:
            txn2.save()
        self.assertIn("amount", ctx2.exception.message_dict)

    def test_transaction_entry_creation(self):
        txn = Transaction.objects.create(**self.transaction_data)
        entry = TransactionEntry.objects.create(
            transaction=txn,
            account=self.account,
            entry_type=TransactionEntry.EntryType.CREDIT,
            amount=Decimal("5000.00"),
        )
        self.assertEqual(entry.transaction, txn)
        self.assertEqual(entry.account, self.account)
        self.assertEqual(entry.entry_type, TransactionEntry.EntryType.CREDIT)
        self.assertEqual(entry.amount, Decimal("5000.00"))

    def test_entry_positive_amount_validation(self):
        txn = Transaction.objects.create(**self.transaction_data)
        entry = TransactionEntry(
            transaction=txn,
            account=self.account,
            entry_type=TransactionEntry.EntryType.DEBIT,
            amount=Decimal("0.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            entry.save()
        self.assertIn("amount", ctx.exception.message_dict)

    def test_debit_credit_balance_validation(self):
        txn = Transaction.objects.create(**self.transaction_data)
        TransactionEntry.objects.create(
            transaction=txn,
            account=self.account,
            entry_type=TransactionEntry.EntryType.DEBIT,
            amount=Decimal("5000.00"),
        )
        with self.assertRaises(ValidationError):
            txn.validate_entries_balance()

        TransactionEntry.objects.create(
            transaction=txn,
            account=self.account,
            entry_type=TransactionEntry.EntryType.CREDIT,
            amount=Decimal("5000.00"),
        )
        txn.validate_entries_balance()

    def test_no_entries_balance_validation_fails(self):
        txn = Transaction.objects.create(**self.transaction_data)
        with self.assertRaises(ValidationError) as ctx:
            txn.validate_entries_balance()
        self.assertIn("at least one entry", str(ctx.exception))


class DepositServiceTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
            is_active=True,
        )
        self.user = User.objects.create_user(username="teller1", password="Password123!")
        StaffProfile.objects.create(user=self.user, employee_id="EMP_DEP_T1", branch=self.branch, is_active=True)
        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.manager = User.objects.create_user(username="manager1", password="Password123!")
        self.manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=self.manager, employee_id="EMP_DEP_M1", branch=self.branch, is_active=True)

        self.customer = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Rahim Uddin",
            date_of_birth=date(1985, 3, 20),
            nid_number="1985123456789",
            phone="01811111111",
            present_address="45 Gulshan, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.user,
            status=Customer.Status.ACTIVE,
        )
        self.product = AccountProduct.objects.get(product_code="SAV")
        self.account = Account.objects.create(
            customer=self.customer,
            product=self.product,
            branch=self.branch,
        )

    def test_deposit_creation_starts_pending_without_balance_change(self):
        amount = Decimal("10000.00")
        txn = deposit(
            account=self.account,
            amount=amount,
            created_by=self.user,
            description="Cash deposit at counter",
        )

        # Deposit initially starts PENDING
        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.authorization_status, Transaction.AuthorizationStatus.PENDING)

        # Balance remains 0.00 before approval
        self.account.refresh_from_db()
        self.assertEqual(self.account.available_balance, Decimal("0.00"))

        # Entries are created
        entries = txn.entries.all()
        self.assertEqual(entries.count(), 2)

    def test_deposit_approval_posts_transaction_and_updates_balance(self):
        amount = Decimal("10000.00")
        txn = deposit(
            account=self.account,
            amount=amount,
            created_by=self.user,
            description="Cash deposit at counter",
        )

        # Manager approves
        approved_txn = approve_transaction(transaction=txn, checker_user=self.manager)

        self.assertEqual(approved_txn.authorization_status, Transaction.AuthorizationStatus.APPROVED)
        self.assertEqual(approved_txn.status, Transaction.Status.POSTED)

        # Balance updated after approval
        self.account.refresh_from_db()
        self.assertEqual(self.account.available_balance, amount)
        self.assertEqual(self.account.ledger_balance, amount)

    def test_deposit_rejection_does_not_update_balance(self):
        amount = Decimal("10000.00")
        txn = deposit(
            account=self.account,
            amount=amount,
            created_by=self.user,
            description="Suspicious deposit",
        )

        # Manager rejects
        rejected_txn = reject_transaction(transaction=txn, checker_user=self.manager, reason="Unclear origin")

        self.assertEqual(rejected_txn.authorization_status, Transaction.AuthorizationStatus.REJECTED)
        self.assertEqual(rejected_txn.status, Transaction.Status.REJECTED)

        # Balance remains unchanged
        self.account.refresh_from_db()
        self.assertEqual(self.account.available_balance, Decimal("0.00"))

    def test_inactive_account_rejection(self):
        self.account.account_status = Account.AccountStatus.FROZEN
        self.account.save()

        with self.assertRaises(ValidationError) as ctx:
            deposit(
                account=self.account,
                amount=Decimal("1000.00"),
                created_by=self.user,
            )
        self.assertIn("ACTIVE", str(ctx.exception))

    def test_zero_amount_rejection(self):
        with self.assertRaises(ValidationError) as ctx:
            deposit(
                account=self.account,
                amount=Decimal("0.00"),
                created_by=self.user,
            )
        self.assertIn("positive", str(ctx.exception))

    def test_deposit_api_endpoint(self):
        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.post('/api/transactions/deposit/', {
            "account_number": self.account.account_number,
            "amount": "2500.00",
            "description": "Counter deposit API",
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['account_number'], self.account.account_number)

        # Balance is still 0.00 until approval
        self.account.refresh_from_db()
        self.assertEqual(self.account.available_balance, Decimal("0.00"))


class WithdrawalServiceTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
            is_active=True,
        )
        self.user = User.objects.create_user(username="teller1", password="Password123!")
        StaffProfile.objects.create(user=self.user, employee_id="EMP_WDR_T1", branch=self.branch, is_active=True)
        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.manager = User.objects.create_user(username="manager1", password="Password123!")
        self.manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=self.manager, employee_id="EMP_WDR_M1", branch=self.branch, is_active=True)

        self.customer = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Rahim Uddin",
            date_of_birth=date(1985, 3, 20),
            nid_number="1985123456789",
            phone="01811111111",
            present_address="45 Gulshan, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.user,
            status=Customer.Status.ACTIVE,
        )
        self.product = AccountProduct.objects.get(product_code="SAV")
        self.account = Account.objects.create(
            customer=self.customer,
            product=self.product,
            branch=self.branch,
        )

        # Fund account via deposit + approval
        dep_txn = deposit(account=self.account, amount=Decimal("15000.00"), created_by=self.user)
        approve_transaction(dep_txn, checker_user=self.manager)
        self.account.refresh_from_db()

    def test_withdrawal_starts_pending_without_balance_reduction(self):
        initial_balance = self.account.available_balance
        withdraw_amount = Decimal("5000.00")

        txn = withdraw(
            account=self.account,
            amount=withdraw_amount,
            created_by=self.user,
            description="ATM cash withdrawal",
        )

        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.authorization_status, Transaction.AuthorizationStatus.PENDING)

        # Balance remains unchanged before approval
        self.account.refresh_from_db()
        self.assertEqual(self.account.available_balance, initial_balance)

    def test_withdrawal_approval_reduces_balance(self):
        initial_balance = self.account.available_balance
        withdraw_amount = Decimal("5000.00")

        txn = withdraw(
            account=self.account,
            amount=withdraw_amount,
            created_by=self.user,
            description="ATM cash withdrawal",
        )

        approved_txn = approve_transaction(transaction=txn, checker_user=self.manager)

        self.assertEqual(approved_txn.authorization_status, Transaction.AuthorizationStatus.APPROVED)
        self.assertEqual(approved_txn.status, Transaction.Status.POSTED)

        self.account.refresh_from_db()
        self.assertEqual(self.account.available_balance, initial_balance - withdraw_amount)

    def test_withdrawal_rejection_does_not_reduce_balance(self):
        initial_balance = self.account.available_balance

        txn = withdraw(
            account=self.account,
            amount=Decimal("5000.00"),
            created_by=self.user,
        )

        rejected_txn = reject_transaction(txn, checker_user=self.manager, reason="Signature mismatch")
        self.assertEqual(rejected_txn.status, Transaction.Status.REJECTED)

        self.account.refresh_from_db()
        self.assertEqual(self.account.available_balance, initial_balance)

    def test_insufficient_balance_rejection(self):
        excessive_amount = self.account.available_balance + Decimal("1000.00")

        with self.assertRaises(ValidationError) as ctx:
            withdraw(
                account=self.account,
                amount=excessive_amount,
                created_by=self.user,
            )
        self.assertIn("Insufficient", str(ctx.exception))

    def test_inactive_account_rejection(self):
        self.account.account_status = Account.AccountStatus.FROZEN
        self.account.save()

        with self.assertRaises(ValidationError) as ctx:
            withdraw(
                account=self.account,
                amount=Decimal("1000.00"),
                created_by=self.user,
            )
        self.assertIn("ACTIVE", str(ctx.exception))


class TransferServiceTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
            is_active=True,
        )
        self.user = User.objects.create_user(username="teller1", password="Password123!")
        StaffProfile.objects.create(user=self.user, employee_id="EMP_TRF_T1", branch=self.branch, is_active=True)
        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.manager = User.objects.create_user(username="manager1", password="Password123!")
        self.manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=self.manager, employee_id="EMP_TRF_M1", branch=self.branch, is_active=True)

        self.customer1 = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Rahim Uddin",
            date_of_birth=date(1985, 3, 20),
            nid_number="1985123456789",
            phone="01811111111",
            present_address="45 Gulshan, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.user,
            status=Customer.Status.ACTIVE,
        )
        self.customer2 = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Karim Chowdhury",
            date_of_birth=date(1992, 8, 10),
            nid_number="1992987654321",
            phone="01722222222",
            present_address="12 Dhanmondi, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.user,
            status=Customer.Status.ACTIVE,
        )

        self.product = AccountProduct.objects.get(product_code="SAV")

        self.sender_account = Account.objects.create(
            customer=self.customer1,
            product=self.product,
            branch=self.branch,
        )
        self.receiver_account = Account.objects.create(
            customer=self.customer2,
            product=self.product,
            branch=self.branch,
        )

        # Fund sender account with 20,000 BDT via deposit + approval
        dep_txn = deposit(account=self.sender_account, amount=Decimal("20000.00"), created_by=self.user)
        approve_transaction(dep_txn, checker_user=self.manager)

        self.sender_account.refresh_from_db()
        self.receiver_account.refresh_from_db()

    def test_transfer_starts_pending_without_balance_change(self):
        sender_initial = self.sender_account.available_balance
        receiver_initial = self.receiver_account.available_balance
        transfer_amount = Decimal("5000.00")

        txn = transfer(
            from_account=self.sender_account,
            to_account=self.receiver_account,
            amount=transfer_amount,
            created_by=self.user,
            description="Fund transfer to Karim",
        )

        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.authorization_status, Transaction.AuthorizationStatus.PENDING)

        # Balances remain unchanged before approval
        self.sender_account.refresh_from_db()
        self.receiver_account.refresh_from_db()
        self.assertEqual(self.sender_account.available_balance, sender_initial)
        self.assertEqual(self.receiver_account.available_balance, receiver_initial)

    def test_transfer_approval_posts_and_updates_both_balances(self):
        sender_initial = self.sender_account.available_balance
        receiver_initial = self.receiver_account.available_balance
        transfer_amount = Decimal("5000.00")

        txn = transfer(
            from_account=self.sender_account,
            to_account=self.receiver_account,
            amount=transfer_amount,
            created_by=self.user,
            description="Fund transfer to Karim",
        )

        approved_txn = approve_transaction(transaction=txn, checker_user=self.manager)

        self.assertEqual(approved_txn.status, Transaction.Status.POSTED)
        self.assertEqual(approved_txn.authorization_status, Transaction.AuthorizationStatus.APPROVED)

        # Sender reduced
        self.sender_account.refresh_from_db()
        self.assertEqual(self.sender_account.available_balance, sender_initial - transfer_amount)

        # Receiver increased
        self.receiver_account.refresh_from_db()
        self.assertEqual(self.receiver_account.available_balance, receiver_initial + transfer_amount)

    def test_transfer_rejection_leaves_balances_unchanged(self):
        sender_initial = self.sender_account.available_balance
        receiver_initial = self.receiver_account.available_balance

        txn = transfer(
            from_account=self.sender_account,
            to_account=self.receiver_account,
            amount=Decimal("5000.00"),
            created_by=self.user,
        )

        rejected_txn = reject_transaction(txn, checker_user=self.manager, reason="Invalid beneficiary info")
        self.assertEqual(rejected_txn.status, Transaction.Status.REJECTED)

        self.sender_account.refresh_from_db()
        self.receiver_account.refresh_from_db()
        self.assertEqual(self.sender_account.available_balance, sender_initial)
        self.assertEqual(self.receiver_account.available_balance, receiver_initial)


class MakerCheckerAuthorizationTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
            is_active=True,
        )

        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.teller_group, _ = Group.objects.get_or_create(name='Teller')

        self.maker_teller = User.objects.create_user(username="maker_teller", password="Password123!")
        self.maker_teller.groups.add(self.teller_group)
        StaffProfile.objects.create(user=self.maker_teller, employee_id="EMP_MC_T1", branch=self.branch, is_active=True)

        self.other_teller = User.objects.create_user(username="other_teller", password="Password123!")
        self.other_teller.groups.add(self.teller_group)
        StaffProfile.objects.create(user=self.other_teller, employee_id="EMP_MC_T2", branch=self.branch, is_active=True)

        self.checker_manager = User.objects.create_user(username="checker_manager", password="Password123!")
        self.checker_manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=self.checker_manager, employee_id="EMP_MC_M1", branch=self.branch, is_active=True)

        self.maker_manager = User.objects.create_user(username="maker_manager", password="Password123!")
        self.maker_manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=self.maker_manager, employee_id="EMP_MC_M2", branch=self.branch, is_active=True)

        self.customer = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Rahim Uddin",
            date_of_birth=date(1985, 3, 20),
            nid_number="1985123456789",
            phone="01811111111",
            present_address="45 Gulshan, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.maker_teller,
            status=Customer.Status.ACTIVE,
        )
        self.product = AccountProduct.objects.get(product_code="SAV")
        self.account = Account.objects.create(
            customer=self.customer,
            product=self.product,
            branch=self.branch,
        )

    def test_pending_transaction_creation(self):
        txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=self.maker_teller)
        self.assertEqual(txn.authorization_status, Transaction.AuthorizationStatus.PENDING)
        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertIsNone(txn.approved_by)
        self.assertIsNone(txn.approved_at)

    def test_manager_approval_success(self):
        txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=self.maker_teller)
        approved_txn = approve_transaction(transaction=txn, checker_user=self.checker_manager)

        self.assertEqual(approved_txn.authorization_status, Transaction.AuthorizationStatus.APPROVED)
        self.assertEqual(approved_txn.status, Transaction.Status.POSTED)
        self.assertEqual(approved_txn.approved_by, self.checker_manager)
        self.assertIsNotNone(approved_txn.approved_at)

    def test_teller_cannot_approve(self):
        txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=self.maker_teller)
        with self.assertRaises(ValidationError) as ctx:
            approve_transaction(transaction=txn, checker_user=self.other_teller)
        self.assertIn("Manager", str(ctx.exception))

    def test_maker_cannot_approve_own_transaction(self):
        txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=self.maker_manager)
        with self.assertRaises(ValidationError) as ctx:
            approve_transaction(transaction=txn, checker_user=self.maker_manager)
        self.assertIn("own transaction", str(ctx.exception))

    def test_rejection_success(self):
        txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=self.maker_teller)
        rejected_txn = reject_transaction(
            transaction=txn,
            checker_user=self.checker_manager,
            reason="Unexplained deposit source",
        )

        self.assertEqual(rejected_txn.authorization_status, Transaction.AuthorizationStatus.REJECTED)
        self.assertEqual(rejected_txn.status, Transaction.Status.REJECTED)
        self.assertEqual(rejected_txn.approved_by, self.checker_manager)
        self.assertEqual(rejected_txn.rejection_reason, "Unexplained deposit source")

    def test_cannot_approve_already_approved_transaction(self):
        txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=self.maker_teller)
        approve_transaction(transaction=txn, checker_user=self.checker_manager)

        other_manager = User.objects.create_user(username="other_manager", password="Password123!")
        other_manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=other_manager, employee_id="EMP_MC_OM1", branch=self.branch, is_active=True)

        with self.assertRaises(ValidationError) as ctx:
            approve_transaction(transaction=txn, checker_user=other_manager)
        self.assertIn("Only PENDING", str(ctx.exception))

    def test_failed_posting_rolls_back_approval(self):
        txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=self.maker_teller)

        # Mock post_transaction to simulate a failure during posting
        with patch('transactions.services.authorization_service.post_transaction', side_effect=Exception("Posting failed")):
            with self.assertRaises(Exception):
                approve_transaction(transaction=txn, checker_user=self.checker_manager)

        # Confirm state rolled back
        txn.refresh_from_db()
        self.assertEqual(txn.authorization_status, Transaction.AuthorizationStatus.PENDING)
        self.assertEqual(txn.status, Transaction.Status.PENDING)


class TransactionCreationAuditTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
            is_active=True,
        )
        self.teller = User.objects.create_user(username="audit_teller", password="Password123!")
        StaffProfile.objects.create(user=self.teller, employee_id="EMP_AUD_T1", branch=self.branch, is_active=True)
        self.customer1 = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Abdur Rahim",
            date_of_birth=date(1988, 5, 12),
            nid_number="1988123456789",
            phone="01710000001",
            present_address="10 Motijheel, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.teller,
            status=Customer.Status.ACTIVE,
        )
        self.customer2 = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Fatema Begum",
            date_of_birth=date(1990, 8, 22),
            nid_number="1990987654321",
            phone="01710000002",
            present_address="20 Dhanmondi, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.teller,
            status=Customer.Status.ACTIVE,
        )
        self.product = AccountProduct.objects.get(product_code="SAV")
        self.account1 = Account.objects.create(
            customer=self.customer1,
            product=self.product,
            branch=self.branch,
        )
        self.account2 = Account.objects.create(
            customer=self.customer2,
            product=self.product,
            branch=self.branch,
        )

    def test_deposit_creation_creates_audit_log(self):
        """Verify that successful deposit creation automatically creates an AuditLog with correct details."""
        initial_log_count = AuditLog.objects.count()

        txn = deposit(
            account=self.account1,
            amount=Decimal("15000.00"),
            created_by=self.teller,
            description="Customer cash deposit",
        )

        self.assertEqual(AuditLog.objects.count(), initial_log_count + 1)
        audit = AuditLog.objects.filter(object_id=txn.transaction_id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.user, self.teller)
        self.assertEqual(audit.action, "CREATE_DEPOSIT")
        self.assertEqual(audit.model_name, "Transaction")
        self.assertEqual(audit.object_id, txn.transaction_id)
        self.assertIn("15000.00", audit.description)
        self.assertIn(self.account1.account_number, audit.description)
        self.assertIn("Customer cash deposit", audit.description)

    def test_withdrawal_creation_creates_audit_log(self):
        """Verify that successful withdrawal creation automatically creates an AuditLog with correct details."""
        # Fund account directly for withdrawal setup
        self.account1.available_balance = Decimal("25000.00")
        self.account1.ledger_balance = Decimal("25000.00")
        self.account1.save()

        initial_log_count = AuditLog.objects.count()

        txn = withdraw(
            account=self.account1,
            amount=Decimal("7000.00"),
            created_by=self.teller,
            description="Branch counter withdrawal",
        )

        self.assertEqual(AuditLog.objects.count(), initial_log_count + 1)
        audit = AuditLog.objects.filter(object_id=txn.transaction_id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.user, self.teller)
        self.assertEqual(audit.action, "CREATE_WITHDRAWAL")
        self.assertEqual(audit.model_name, "Transaction")
        self.assertEqual(audit.object_id, txn.transaction_id)
        self.assertIn("7000.00", audit.description)
        self.assertIn(self.account1.account_number, audit.description)
        self.assertIn("Branch counter withdrawal", audit.description)

    def test_transfer_creation_creates_audit_log(self):
        """Verify that successful transfer creation automatically creates an AuditLog with correct details."""
        # Fund sender account
        self.account1.available_balance = Decimal("50000.00")
        self.account1.ledger_balance = Decimal("50000.00")
        self.account1.save()

        initial_log_count = AuditLog.objects.count()

        txn = transfer(
            from_account=self.account1,
            to_account=self.account2,
            amount=Decimal("12000.00"),
            created_by=self.teller,
            description="Inter-account tuition transfer",
        )

        self.assertEqual(AuditLog.objects.count(), initial_log_count + 1)
        audit = AuditLog.objects.filter(object_id=txn.transaction_id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.user, self.teller)
        self.assertEqual(audit.action, "CREATE_TRANSFER")
        self.assertEqual(audit.model_name, "Transaction")
        self.assertEqual(audit.object_id, txn.transaction_id)
        self.assertIn("12000.00", audit.description)
        self.assertIn(self.account1.account_number, audit.description)
        self.assertIn(self.account2.account_number, audit.description)
        self.assertIn("Inter-account tuition transfer", audit.description)

    def test_failed_transaction_does_not_create_audit_log(self):
        """Verify that failed transaction attempts do not produce audit log records."""
        initial_log_count = AuditLog.objects.count()

        # 1. Invalid amount deposit
        with self.assertRaises(ValidationError):
            deposit(account=self.account1, amount=Decimal("-100.00"), created_by=self.teller)

        # 2. Insufficient balance withdrawal
        with self.assertRaises(ValidationError):
            withdraw(account=self.account1, amount=Decimal("999999.00"), created_by=self.teller)

        # 3. Same-account transfer
        with self.assertRaises(ValidationError):
            transfer(from_account=self.account1, to_account=self.account1, amount=Decimal("100.00"), created_by=self.teller)

        # Confirm no audit logs were created
        self.assertEqual(AuditLog.objects.count(), initial_log_count)


class TransactionAuthorizationAuditTest(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            branch_code="BR001",
            branch_name="Main Branch",
            district="Dhaka",
            address="123 Motijheel C/A",
            is_active=True,
        )

        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.teller_group, _ = Group.objects.get_or_create(name='Teller')

        self.maker_teller = User.objects.create_user(username="maker_teller_auth", password="Password123!")
        self.maker_teller.groups.add(self.teller_group)
        StaffProfile.objects.create(user=self.maker_teller, employee_id="EMP_AUTH_T1", branch=self.branch, is_active=True)

        self.other_teller = User.objects.create_user(username="other_teller_auth", password="Password123!")
        self.other_teller.groups.add(self.teller_group)
        StaffProfile.objects.create(user=self.other_teller, employee_id="EMP_AUTH_T2", branch=self.branch, is_active=True)

        self.checker_manager = User.objects.create_user(username="checker_manager_auth", password="Password123!")
        self.checker_manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=self.checker_manager, employee_id="EMP_AUTH_M1", branch=self.branch, is_active=True)

        self.customer = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Abdur Rahim",
            date_of_birth=date(1985, 3, 20),
            nid_number="1985123456789",
            phone="01811111111",
            present_address="45 Gulshan, Dhaka",
            district="Dhaka",
            home_branch=self.branch,
            created_by=self.maker_teller,
            status=Customer.Status.ACTIVE,
        )
        self.product = AccountProduct.objects.get(product_code="SAV")
        self.account = Account.objects.create(
            customer=self.customer,
            product=self.product,
            branch=self.branch,
        )

    def test_approval_creates_audit_log(self):
        """Verify that successful approval creates an AuditLog with correct checker user, action, object_id, and description."""
        txn = deposit(account=self.account, amount=Decimal("10000.00"), created_by=self.maker_teller)

        initial_count = AuditLog.objects.filter(action="APPROVE_TRANSACTION").count()

        approved_txn = approve_transaction(transaction=txn, checker_user=self.checker_manager)

        self.assertEqual(AuditLog.objects.filter(action="APPROVE_TRANSACTION").count(), initial_count + 1)
        audit = AuditLog.objects.filter(action="APPROVE_TRANSACTION", object_id=txn.transaction_id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.user, self.checker_manager)
        self.assertEqual(audit.action, "APPROVE_TRANSACTION")
        self.assertEqual(audit.model_name, "Transaction")
        self.assertEqual(audit.object_id, txn.transaction_id)
        self.assertIn("Approved", audit.description)
        self.assertIn(txn.transaction_id, audit.description)
        self.assertIn("10000.00", audit.description)

    def test_rejection_creates_audit_log(self):
        """Verify that successful rejection creates an AuditLog with checker user, action, object_id, and reason."""
        txn = deposit(account=self.account, amount=Decimal("5000.00"), created_by=self.maker_teller)

        initial_count = AuditLog.objects.filter(action="REJECT_TRANSACTION").count()
        rejection_reason = "Customer signature does not match records"

        rejected_txn = reject_transaction(
            transaction=txn,
            checker_user=self.checker_manager,
            reason=rejection_reason,
        )

        self.assertEqual(AuditLog.objects.filter(action="REJECT_TRANSACTION").count(), initial_count + 1)
        audit = AuditLog.objects.filter(action="REJECT_TRANSACTION", object_id=txn.transaction_id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.user, self.checker_manager)
        self.assertEqual(audit.action, "REJECT_TRANSACTION")
        self.assertEqual(audit.model_name, "Transaction")
        self.assertEqual(audit.object_id, txn.transaction_id)
        self.assertIn("Rejected", audit.description)
        self.assertIn(txn.transaction_id, audit.description)
        self.assertIn(rejection_reason, audit.description)

    def test_failed_approval_does_not_create_audit_log(self):
        """Verify that failed approval attempts (role check, maker-checker, posting error) do not create audit log."""
        txn = deposit(account=self.account, amount=Decimal("2000.00"), created_by=self.maker_teller)

        # 1. Non-manager attempts approval
        with self.assertRaises(ValidationError):
            approve_transaction(transaction=txn, checker_user=self.other_teller)
        self.assertEqual(AuditLog.objects.filter(action="APPROVE_TRANSACTION").count(), 0)

        # 2. Maker attempts to approve own transaction (maker is in Manager group)
        maker_manager = User.objects.create_user(username="maker_mgr", password="Password123!")
        maker_manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=maker_manager, employee_id="EMP_AUTH_MM1", branch=self.branch, is_active=True)
        mgr_txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=maker_manager)

        with self.assertRaises(ValidationError):
            approve_transaction(transaction=mgr_txn, checker_user=maker_manager)
        self.assertEqual(AuditLog.objects.filter(action="APPROVE_TRANSACTION").count(), 0)

        # 3. Failed posting rolls back approval and does NOT create audit log
        with patch('transactions.services.authorization_service.post_transaction', side_effect=Exception("Posting failure")):
            with self.assertRaises(Exception):
                approve_transaction(transaction=txn, checker_user=self.checker_manager)
        self.assertEqual(AuditLog.objects.filter(action="APPROVE_TRANSACTION").count(), 0)

    def test_failed_rejection_does_not_create_audit_log(self):
        """Verify that failed rejection attempts do not create audit log."""
        txn = deposit(account=self.account, amount=Decimal("2000.00"), created_by=self.maker_teller)

        # 1. Non-manager attempts rejection
        with self.assertRaises(ValidationError):
            reject_transaction(transaction=txn, checker_user=self.other_teller, reason="Unauthorized")
        self.assertEqual(AuditLog.objects.filter(action="REJECT_TRANSACTION").count(), 0)

        # 2. Maker attempts to reject own transaction
        maker_manager = User.objects.create_user(username="maker_mgr2", password="Password123!")
        maker_manager.groups.add(self.manager_group)
        StaffProfile.objects.create(user=maker_manager, employee_id="EMP_AUTH_MM2", branch=self.branch, is_active=True)
        mgr_txn = deposit(account=self.account, amount=Decimal("1000.00"), created_by=maker_manager)

        with self.assertRaises(ValidationError):
            reject_transaction(transaction=mgr_txn, checker_user=maker_manager, reason="Self reject")
        self.assertEqual(AuditLog.objects.filter(action="REJECT_TRANSACTION").count(), 0)


class TransactionBranchAccessControlTest(TestCase):
    def setUp(self):
        # 1. Create Branches
        self.branch_a = Branch.objects.create(
            branch_code="BR_DAC",
            branch_name="Dhaka Main Branch",
            district="Dhaka",
            address="Motijheel C/A",
            is_active=True,
        )
        self.branch_b = Branch.objects.create(
            branch_code="BR_CTG",
            branch_name="Chittagong Branch",
            district="Chittagong",
            address="Agrabad C/A",
            is_active=True,
        )

        # 2. Create Staff in Branch A
        self.teller_a = User.objects.create_user(username="teller_a", password="Password123!")
        StaffProfile.objects.create(
            user=self.teller_a,
            employee_id="EMP_BR_TA",
            branch=self.branch_a,
            is_active=True,
        )

        # 3. Create Staff in Branch B
        self.teller_b = User.objects.create_user(username="teller_b", password="Password123!")
        StaffProfile.objects.create(
            user=self.teller_b,
            employee_id="EMP_BR_TB",
            branch=self.branch_b,
            is_active=True,
        )

        # 4. Superuser
        self.superuser = User.objects.create_superuser(
            username="super_maker",
            email="super@agranicbs.com",
            password="Password123!",
        )

        # 5. Product & Customers & Accounts
        self.product = AccountProduct.objects.get(product_code="SAV")

        self.customer_a = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Customer A",
            date_of_birth=date(1990, 1, 1),
            nid_number="NID_A_001",
            phone="01700000001",
            present_address="Dhaka",
            district="Dhaka",
            home_branch=self.branch_a,
            created_by=self.teller_a,
            status=Customer.Status.ACTIVE,
        )
        self.account_a = Account.objects.create(
            customer=self.customer_a,
            product=self.product,
            branch=self.branch_a,
            available_balance=Decimal("50000.00"),
            ledger_balance=Decimal("50000.00"),
        )

        self.customer_b = Customer.objects.create(
            customer_type=Customer.CustomerType.INDIVIDUAL,
            full_name="Customer B",
            date_of_birth=date(1992, 2, 2),
            nid_number="NID_B_002",
            phone="01700000002",
            present_address="Chittagong",
            district="Chittagong",
            home_branch=self.branch_b,
            created_by=self.teller_b,
            status=Customer.Status.ACTIVE,
        )
        self.account_b = Account.objects.create(
            customer=self.customer_b,
            product=self.product,
            branch=self.branch_b,
            available_balance=Decimal("30000.00"),
            ledger_balance=Decimal("30000.00"),
        )

    # --- Deposit Tests ---
    def test_deposit_same_branch_success(self):
        initial_audit_count = AuditLog.objects.filter(action="CREATE_DEPOSIT").count()
        txn = deposit(
            account=self.account_a,
            amount=Decimal("5000.00"),
            created_by=self.teller_a,
            description="Branch A teller depositing to Branch A account",
        )
        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.account, self.account_a)
        self.assertEqual(txn.created_by, self.teller_a)
        self.assertEqual(AuditLog.objects.filter(action="CREATE_DEPOSIT").count(), initial_audit_count + 1)

    def test_deposit_different_branch_failure(self):
        with self.assertRaises(ValidationError) as ctx:
            deposit(
                account=self.account_a,
                amount=Decimal("5000.00"),
                created_by=self.teller_b,
                description="Branch B teller depositing to Branch A account",
            )
        self.assertIn("created_by", ctx.exception.message_dict)

    def test_deposit_different_branch_creates_no_audit_log(self):
        initial_audit_count = AuditLog.objects.count()
        with self.assertRaises(ValidationError):
            deposit(
                account=self.account_a,
                amount=Decimal("5000.00"),
                created_by=self.teller_b,
            )
        self.assertEqual(AuditLog.objects.count(), initial_audit_count)

    # --- Withdrawal Tests ---
    def test_withdrawal_same_branch_success(self):
        initial_audit_count = AuditLog.objects.filter(action="CREATE_WITHDRAWAL").count()
        txn = withdraw(
            account=self.account_a,
            amount=Decimal("2000.00"),
            created_by=self.teller_a,
            description="Branch A teller withdrawing from Branch A account",
        )
        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.account, self.account_a)
        self.assertEqual(txn.created_by, self.teller_a)
        self.assertEqual(AuditLog.objects.filter(action="CREATE_WITHDRAWAL").count(), initial_audit_count + 1)

    def test_withdrawal_different_branch_failure(self):
        with self.assertRaises(ValidationError) as ctx:
            withdraw(
                account=self.account_a,
                amount=Decimal("2000.00"),
                created_by=self.teller_b,
                description="Branch B teller withdrawing from Branch A account",
            )
        self.assertIn("created_by", ctx.exception.message_dict)

    def test_withdrawal_different_branch_creates_no_audit_log(self):
        initial_audit_count = AuditLog.objects.count()
        with self.assertRaises(ValidationError):
            withdraw(
                account=self.account_a,
                amount=Decimal("2000.00"),
                created_by=self.teller_b,
            )
        self.assertEqual(AuditLog.objects.count(), initial_audit_count)

    # --- Transfer Tests ---
    def test_transfer_same_source_branch_success(self):
        # Maker belongs to Branch A (source account branch). Destination account is Branch B.
        initial_audit_count = AuditLog.objects.filter(action="CREATE_TRANSFER").count()
        txn = transfer(
            from_account=self.account_a,
            to_account=self.account_b,
            amount=Decimal("3000.00"),
            created_by=self.teller_a,
            description="Branch A teller transferring from Branch A to Branch B",
        )
        self.assertEqual(txn.status, Transaction.Status.PENDING)
        self.assertEqual(txn.account, self.account_a)
        self.assertEqual(txn.created_by, self.teller_a)
        self.assertEqual(AuditLog.objects.filter(action="CREATE_TRANSFER").count(), initial_audit_count + 1)

    def test_transfer_different_source_branch_failure(self):
        # Maker belongs to Branch B, but source account is in Branch A -> must fail
        with self.assertRaises(ValidationError) as ctx:
            transfer(
                from_account=self.account_a,
                to_account=self.account_b,
                amount=Decimal("3000.00"),
                created_by=self.teller_b,
                description="Branch B teller transferring from Branch A to Branch B",
            )
        self.assertIn("created_by", ctx.exception.message_dict)

    def test_transfer_different_branch_creates_no_audit_log(self):
        initial_audit_count = AuditLog.objects.count()
        with self.assertRaises(ValidationError):
            transfer(
                from_account=self.account_a,
                to_account=self.account_b,
                amount=Decimal("3000.00"),
                created_by=self.teller_b,
            )
        self.assertEqual(AuditLog.objects.count(), initial_audit_count)

    # --- Superuser Bypass Tests ---
    def test_superuser_can_operate_across_branches(self):
        # Superuser can deposit to Branch A
        dep_txn = deposit(
            account=self.account_a,
            amount=Decimal("1000.00"),
            created_by=self.superuser,
        )
        self.assertEqual(dep_txn.status, Transaction.Status.PENDING)

        # Superuser can withdraw from Branch B
        wdr_txn = withdraw(
            account=self.account_b,
            amount=Decimal("1000.00"),
            created_by=self.superuser,
        )
        self.assertEqual(wdr_txn.status, Transaction.Status.PENDING)

        # Superuser can transfer from Branch A to Branch B
        trf_txn = transfer(
            from_account=self.account_a,
            to_account=self.account_b,
            amount=Decimal("1000.00"),
            created_by=self.superuser,
        )
        self.assertEqual(trf_txn.status, Transaction.Status.PENDING)



