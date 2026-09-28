"""
Internal Fund Transfer Service

Architectural assumptions:
- All transfer logic is isolated in this service layer.
- Creates a PENDING transfer transaction and double-entry records.
- Balances are NOT modified at creation; balance transfer occurs upon Manager approval.
- Enforces positive Decimal amounts, active account status, distinct accounts, and initial sender balance.
"""
from decimal import Decimal
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError

from accounts.models import Account
from audit.models import AuditLog
from transactions.models import Transaction, TransactionEntry


def transfer(
    from_account: Account,
    to_account: Account,
    amount: Decimal,
    created_by,
    description: str = "",
) -> Transaction:
    """
    Initiate an internal fund transfer from one account to another.
    Creates a PENDING transaction requiring Manager approval before posting.

    Args:
        from_account: The sender Account instance to debit.
        to_account:   The receiver Account instance to credit.
        amount:       Transfer amount as Decimal. Must be > 0.
        created_by:   Django User performing the transfer.
        description:  Optional narrative for the transaction.

    Returns:
        The created PENDING Transaction instance.

    Raises:
        ValidationError: If accounts are invalid, inactive, identical, amount is not positive,
                         or sender has insufficient balance.
        ValueError:      If a non-Decimal amount is provided.
    """
    # --- Guard: enforce Decimal ---
    if not isinstance(amount, Decimal):
        raise ValueError("amount must be a Decimal instance, not float or other type.")

    # --- Guard: positive amount ---
    if amount <= Decimal("0.00"):
        raise ValidationError({"amount": "Transfer amount must be positive."})

    # --- Guard: cannot transfer to same account ---
    if from_account.pk == to_account.pk:
        raise ValidationError({"to_account": "Source and destination accounts cannot be the same."})

    # --- Guard: initial account status checks ---
    if from_account.account_status != Account.AccountStatus.ACTIVE:
        raise ValidationError(
            {"from_account": f"Sender account is not ACTIVE. Current status: {from_account.account_status}."}
        )

    if to_account.account_status != Account.AccountStatus.ACTIVE:
        raise ValidationError(
            {"to_account": f"Receiver account is not ACTIVE. Current status: {to_account.account_status}."}
        )

    # --- Guard: sufficient sender balance ---
    if from_account.available_balance < amount:
        raise ValidationError(
            {"amount": f"Insufficient available balance for transfer. "
                       f"Available: {from_account.available_balance}, Requested: {amount}."}
        )

    with db_transaction.atomic():
        # 1. Create PENDING Transaction record (does NOT update balances)
        txn = Transaction(
            transaction_type=Transaction.TransactionType.TRANSFER,
            account=from_account,
            amount=amount,
            status=Transaction.Status.PENDING,
            authorization_status=Transaction.AuthorizationStatus.PENDING,
            description=description or f"Transfer to {to_account.account_number}",
            created_by=created_by,
        )
        txn.save()

        # 2. Create double-entry records
        # DEBIT sender account (money leaving sender)
        TransactionEntry.objects.create(
            transaction=txn,
            account=from_account,
            entry_type=TransactionEntry.EntryType.DEBIT,
            amount=amount,
        )
        # CREDIT receiver account (money entering receiver)
        TransactionEntry.objects.create(
            transaction=txn,
            account=to_account,
            entry_type=TransactionEntry.EntryType.CREDIT,
            amount=amount,
        )

        # 3. Validate debit == credit entries
        txn.validate_entries_balance()

        # 4. Record audit log
        audit_description = (
            f"Initiated transfer of {amount} from account {from_account.account_number} "
            f"to account {to_account.account_number}"
        )
        if description:
            audit_description += f": {description}"
        AuditLog.objects.create(
            user=created_by,
            action="CREATE_TRANSFER",
            model_name="Transaction",
            object_id=txn.transaction_id,
            description=audit_description,
        )

    return txn
