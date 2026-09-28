"""
Deposit Service

Architectural assumptions:
- All deposit logic is isolated in this service layer.
- Creates a PENDING deposit transaction and double-entry records.
- Balances are NOT modified at creation; balance posting occurs upon Manager approval.
- Enforces positive Decimal amounts and active account status.
"""
from decimal import Decimal
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError

from accounts.models import Account
from audit.models import AuditLog
from transactions.models import Transaction, TransactionEntry


def deposit(account: Account, amount: Decimal, created_by, description: str = "") -> Transaction:
    """
    Initiate a deposit operation on the given account.
    Creates a PENDING transaction requiring Manager approval before posting.

    Args:
        account:     The Account instance to credit.
        amount:      Deposit amount as Decimal. Must be > 0.
        created_by:  Django User performing the deposit.
        description: Optional narrative for the transaction.

    Returns:
        The created PENDING Transaction instance.

    Raises:
        ValidationError: If the account is not ACTIVE, or amount is not positive.
        ValueError:      If a non-Decimal amount is provided.
    """
    # --- Guard: enforce Decimal ---
    if not isinstance(amount, Decimal):
        raise ValueError("amount must be a Decimal instance, not float or other type.")

    # --- Guard: positive amount ---
    if amount <= Decimal("0.00"):
        raise ValidationError({"amount": "Deposit amount must be positive."})

    # --- Guard: account must be ACTIVE ---
    if account.account_status != Account.AccountStatus.ACTIVE:
        raise ValidationError(
            {"account": f"Deposits can only be made to ACTIVE accounts. "
                        f"Current status: {account.account_status}."}
        )

    with db_transaction.atomic():
        # 1. Create PENDING Transaction record (does NOT update balances)
        txn = Transaction(
            transaction_type=Transaction.TransactionType.DEPOSIT,
            account=account,
            amount=amount,
            status=Transaction.Status.PENDING,
            authorization_status=Transaction.AuthorizationStatus.PENDING,
            description=description,
            created_by=created_by,
        )
        txn.save()

        # 2. Create double-entry records
        # CREDIT the customer account (money coming IN)
        TransactionEntry.objects.create(
            transaction=txn,
            account=account,
            entry_type=TransactionEntry.EntryType.CREDIT,
            amount=amount,
        )
        # DEBIT contra entry
        TransactionEntry.objects.create(
            transaction=txn,
            account=account,
            entry_type=TransactionEntry.EntryType.DEBIT,
            amount=amount,
        )

        # 3. Validate debit == credit entries
        txn.validate_entries_balance()

        # 4. Record audit log
        audit_description = f"Initiated deposit of {amount} to account {account.account_number}"
        if description:
            audit_description += f": {description}"
        AuditLog.objects.create(
            user=created_by,
            action="CREATE_DEPOSIT",
            model_name="Transaction",
            object_id=txn.transaction_id,
            description=audit_description,
        )

    return txn
