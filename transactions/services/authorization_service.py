"""
Authorization Service (Maker-Checker Approval & Posting Workflow)

Architectural assumptions:
- Enforces maker-checker authorization controls for financial transactions.
- Only users in the 'Manager' group (or superusers) can act as checkers.
- Makers cannot approve or reject their own transactions.
- Only transactions in PENDING authorization status can be processed.
- Upon Manager approval, authorization_status becomes APPROVED and post_transaction() is called atomically to move balances.
- Upon Manager rejection, authorization_status becomes REJECTED and status becomes REJECTED without balance changes.
"""
from django.utils import timezone
from django.db import transaction as db_transaction
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User

from audit.models import AuditLog
from transactions.models import Transaction
from transactions.services.posting_service import post_transaction


def is_manager(user: User) -> bool:
    """Check if the user belongs to the Manager group or is a superuser."""
    if user.is_superuser:
        return True
    return user.groups.filter(name='Manager').exists()


def approve_transaction(transaction: Transaction, checker_user: User) -> Transaction:
    """
    Approve a pending transaction and post its balance updates.

    Args:
        transaction:  The Transaction instance to approve.
        checker_user: The Django User acting as checker.

    Returns:
        The updated and posted Transaction instance.

    Raises:
        ValidationError: If checker is not a Manager, maker is checker, transaction is not PENDING,
                         or posting fails (e.g. insufficient balance).
    """
    # 1. Role check: Only Managers can approve
    if not is_manager(checker_user):
        raise ValidationError({"checker_user": "Only users with the Manager role can approve transactions."})

    # 2. Maker-checker check: Maker cannot approve own transaction
    if transaction.created_by_id == checker_user.id:
        raise ValidationError({"checker_user": "Maker cannot approve their own transaction."})

    # 3. Status check: Only PENDING transactions can be approved
    if transaction.authorization_status != Transaction.AuthorizationStatus.PENDING:
        raise ValidationError(
            {"authorization_status": f"Only PENDING transactions can be approved. "
                                      f"Current status: {transaction.authorization_status}."}
        )

    with db_transaction.atomic():
        # 4. Apply approval state changes
        transaction.authorization_status = Transaction.AuthorizationStatus.APPROVED
        transaction.approved_by = checker_user
        transaction.approved_at = timezone.now()
        transaction.authorized_by = checker_user
        transaction.save(update_fields=[
            "authorization_status", "approved_by", "approved_at", "authorized_by", "updated_at"
        ])

        # 5. Call posting service to atomically update balances and set status = POSTED
        transaction = post_transaction(transaction)

        # 6. Record audit log
        audit_description = (
            f"Approved {transaction.transaction_type} transaction {transaction.transaction_id} "
            f"of amount {transaction.amount}"
        )
        AuditLog.objects.create(
            user=checker_user,
            action="APPROVE_TRANSACTION",
            model_name="Transaction",
            object_id=transaction.transaction_id,
            description=audit_description,
        )

    return transaction


def reject_transaction(transaction: Transaction, checker_user: User, reason: str = "") -> Transaction:
    """
    Reject a pending transaction without balance changes.

    Args:
        transaction:  The Transaction instance to reject.
        checker_user: The Django User acting as checker.
        reason:       Optional text explanation for rejection.

    Returns:
        The updated Transaction instance (REJECTED status).

    Raises:
        ValidationError: If checker is not a Manager, maker is checker, or transaction is not PENDING.
    """
    # 1. Role check: Only Managers can reject
    if not is_manager(checker_user):
        raise ValidationError({"checker_user": "Only users with the Manager role can reject transactions."})

    # 2. Maker-checker check: Maker cannot reject own transaction
    if transaction.created_by_id == checker_user.id:
        raise ValidationError({"checker_user": "Maker cannot reject their own transaction."})

    # 3. Status check: Only PENDING transactions can be rejected
    if transaction.authorization_status != Transaction.AuthorizationStatus.PENDING:
        raise ValidationError(
            {"authorization_status": f"Only PENDING transactions can be rejected. "
                                      f"Current status: {transaction.authorization_status}."}
        )

    with db_transaction.atomic():
        # 4. Apply rejection state changes
        transaction.authorization_status = Transaction.AuthorizationStatus.REJECTED
        transaction.status = Transaction.Status.REJECTED
        transaction.approved_by = checker_user
        transaction.approved_at = timezone.now()
        transaction.rejection_reason = reason
        transaction.save(update_fields=[
            "authorization_status", "status", "approved_by", "approved_at", "rejection_reason", "updated_at"
        ])

        # 5. Record audit log
        audit_description = (
            f"Rejected {transaction.transaction_type} transaction {transaction.transaction_id} "
            f"of amount {transaction.amount}"
        )
        if reason:
            audit_description += f". Reason: {reason}"
        AuditLog.objects.create(
            user=checker_user,
            action="REJECT_TRANSACTION",
            model_name="Transaction",
            object_id=transaction.transaction_id,
            description=audit_description,
        )

    return transaction
