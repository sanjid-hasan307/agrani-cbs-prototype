"""
Withdrawal Service

Architectural assumptions:
- All withdrawal logic is isolated in this service layer.
- Creates a PENDING withdrawal transaction and double-entry records.
- Balances are NOT reduced at creation; balance reduction occurs upon Manager approval.
- Enforces positive Decimal amounts, active account status, and initial balance sufficiency.
"""
from decimal import Decimal
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError

from accounts.models import Account
from transactions.models import Transaction, TransactionEntry


def withdraw(account: Account, amount: Decimal, created_by, description: str = "") -> Transaction:
    """
    Initiate a withdrawal operation on the given account.
    Creates a PENDING transaction requiring Manager approval before posting.

    Args:
        account:     The Account instance to debit.
        amount:      Withdrawal amount as Decimal. Must be > 0.
        created_by:  Django User performing the withdrawal.
        description: Optional narrative for the transaction.

    Returns:
        The created PENDING Transaction instance.

    Raises:
        ValidationError: If account is not ACTIVE, amount is not positive, or available_balance is insufficient.
        ValueError:      If a non-Decimal amount is provided.
    """
    # --- Guard: enforce Decimal ---
    if not isinstance(amount, Decimal):
        raise ValueError("amount must be a Decimal instance, not float or other type.")

    # --- Guard: positive amount ---
    if amount <= Decimal("0.00"):
        raise ValidationError({"amount": "Withdrawal amount must be positive."})

    # --- Guard: account must be ACTIVE ---
    if account.account_status != Account.AccountStatus.ACTIVE:
        raise ValidationError(
            {"account": f"Withdrawals can only be made from ACTIVE accounts. "
                        f"Current status: {account.account_status}."}
        )

    # --- Guard: sufficient available balance ---
    if account.available_balance < amount:
        raise ValidationError(
            {"amount": f"Insufficient available balance. "
                       f"Available: {account.available_balance}, Requested: {amount}."}
        )

    with db_transaction.atomic():
        # 1. Create PENDING Transaction record (does NOT reduce balances)
        txn = Transaction(
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            account=account,
            amount=amount,
            status=Transaction.Status.PENDING,
            authorization_status=Transaction.AuthorizationStatus.PENDING,
            description=description,
            created_by=created_by,
        )
        txn.save()

        # 2. Create double-entry records
        # DEBIT customer account (money leaving)
        TransactionEntry.objects.create(
            transaction=txn,
            account=account,
            entry_type=TransactionEntry.EntryType.DEBIT,
            amount=amount,
        )
        # CREDIT contra entry
        TransactionEntry.objects.create(
            transaction=txn,
            account=account,
            entry_type=TransactionEntry.EntryType.CREDIT,
            amount=amount,
        )

        # 3. Validate debit == credit entries
        txn.validate_entries_balance()

    return txn
