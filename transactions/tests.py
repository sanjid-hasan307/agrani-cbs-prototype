from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User, Group
from rest_framework.test import APIClient
from rest_framework import status
from branches.models import Branch
from customers.models import Customer
from products.models import AccountProduct
from accounts.models import Account
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
        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.manager = User.objects.create_user(username="manager1", password="Password123!")
        self.manager.groups.add(self.manager_group)

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
        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.manager = User.objects.create_user(username="manager1", password="Password123!")
        self.manager.groups.add(self.manager_group)

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
        self.manager_group, _ = Group.objects.get_or_create(name='Manager')
        self.manager = User.objects.create_user(username="manager1", password="Password123!")
        self.manager.groups.add(self.manager_group)

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

        self.other_teller = User.objects.create_user(username="other_teller", password="Password123!")
        self.other_teller.groups.add(self.teller_group)

        self.checker_manager = User.objects.create_user(username="checker_manager", password="Password123!")
        self.checker_manager.groups.add(self.manager_group)

        self.maker_manager = User.objects.create_user(username="maker_manager", password="Password123!")
        self.maker_manager.groups.add(self.manager_group)

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
