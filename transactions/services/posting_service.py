"""
Posting Service

Architectural assumptions:
- Handles the actual movement of account balances when a transaction is approved.
- Requires transaction.authorization_status == APPROVED.
- Executes within an atomic database transaction.
- Locks account rows using select_for_update() in deterministic order to prevent deadlocks.
- Validates debit and credit entries equality before posting.
- Updates account available_balance and ledger_balance using Decimal only.
- Sets transaction.status = POSTED.
"""
from decimal import Decimal
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError

from accounts.models import Account
from transactions.models import Transaction, TransactionEntry


def post_transaction(transaction: Transaction) -> Transaction:
    """
    Apply balance changes and set transaction status to POSTED for an approved transaction.

    Args:
        transaction: An approved Transaction instance (authorization_status == APPROVED).

    Returns:
        The posted Transaction instance.

    Raises:
        ValidationError: If transaction is not APPROVED, already POSTED, entries are unbalanced,
                         or account has insufficient balance.
    """
    if transaction.authorization_status != Transaction.AuthorizationStatus.APPROVED:
        raise ValidationError(
            {"authorization_status": f"Transaction must be APPROVED to post. "
                                      f"Current authorization_status: {transaction.authorization_status}."}
        )

    if transaction.status == Transaction.Status.POSTED:
        raise ValidationError({"status": "Transaction is already POSTED."})

    with db_transaction.atomic():
        # Validate entry debit/credit balance
        transaction.validate_entries_balance()

        if transaction.transaction_type in (Transaction.TransactionType.DEPOSIT, Transaction.TransactionType.WITHDRAWAL):
            locked_account = Account.objects.select_for_update().get(pk=transaction.account.pk)

            if locked_account.account_status != Account.AccountStatus.ACTIVE:
                raise ValidationError(
                    {"account": f"Account is not ACTIVE. Current status: {locked_account.account_status}."}
                )

            if transaction.transaction_type == Transaction.TransactionType.DEPOSIT:
                locked_account.available_balance += transaction.amount
                locked_account.ledger_balance += transaction.amount
            elif transaction.transaction_type == Transaction.TransactionType.WITHDRAWAL:
                if locked_account.available_balance < transaction.amount:
                    raise ValidationError(
                        {"amount": f"Insufficient available balance for withdrawal. "
                                   f"Available: {locked_account.available_balance}, Requested: {transaction.amount}."}
                    )
                locked_account.available_balance -= transaction.amount
                locked_account.ledger_balance -= transaction.amount

            locked_account.save(update_fields=["available_balance", "ledger_balance", "updated_at"])

        elif transaction.transaction_type == Transaction.TransactionType.TRANSFER:
            entries = transaction.entries.all()
            debit_entry = entries.get(entry_type=TransactionEntry.EntryType.DEBIT)
            credit_entry = entries.get(entry_type=TransactionEntry.EntryType.CREDIT)

            from_acc_pk = debit_entry.account_id
            to_acc_pk = credit_entry.account_id

            # Deterministic lock ordering to prevent deadlocks
            if from_acc_pk < to_acc_pk:
                first_pk, second_pk = from_acc_pk, to_acc_pk
            else:
                first_pk, second_pk = to_acc_pk, from_acc_pk

            locked_first = Account.objects.select_for_update().get(pk=first_pk)
            locked_second = Account.objects.select_for_update().get(pk=second_pk)

            locked_from = locked_first if from_acc_pk == first_pk else locked_second
            locked_to = locked_second if from_acc_pk == first_pk else locked_first

            if locked_from.account_status != Account.AccountStatus.ACTIVE:
                raise ValidationError(
                    {"from_account": f"Sender account is not ACTIVE. Current status: {locked_from.account_status}."}
                )

            if locked_to.account_status != Account.AccountStatus.ACTIVE:
                raise ValidationError(
                    {"to_account": f"Receiver account is not ACTIVE. Current status: {locked_to.account_status}."}
                )

            if locked_from.available_balance < transaction.amount:
                raise ValidationError(
                    {"amount": f"Insufficient available balance for transfer. "
                               f"Available: {locked_from.available_balance}, Requested: {transaction.amount}."}
                )

            locked_from.available_balance -= transaction.amount
            locked_from.ledger_balance -= transaction.amount
            locked_from.save(update_fields=["available_balance", "ledger_balance", "updated_at"])

            locked_to.available_balance += transaction.amount
            locked_to.ledger_balance += transaction.amount
            locked_to.save(update_fields=["available_balance", "ledger_balance", "updated_at"])

        # Mark transaction as POSTED
        transaction.status = Transaction.Status.POSTED
        transaction.save(update_fields=["status", "updated_at"])

    return transaction
