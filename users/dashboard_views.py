"""
CBS Role-Based Dashboard Views (Phase 4)

Provides dashboard views for each banking role:
- Manager  -> /dashboard/manager/
- Teller   -> /dashboard/teller/
- Auditor  -> /dashboard/auditor/

Architectural assumption:
  Role enforcement is handled by the _role_required decorator that inspects
  the authenticated user's Group membership.  A mismatch returns HTTP 403.
  This prevents privilege escalation through URL guessing and keeps access
  control out of templates.
"""
import logging
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Account
from transactions.models import Transaction
from transactions.services.authorization_service import approve_transaction, reject_transaction
from transactions.services.deposit_service import deposit
from transactions.services.withdrawal_service import withdraw
from users.views import get_user_role, get_user_staff_info

logger = logging.getLogger(__name__)


def parse_decimal_amount(amount_raw: str) -> Decimal:
    """
    Safely parses string amount to Decimal.
    Validates finite representation, positive value (> 0), and maximum 2 decimal places.
    """
    amount = Decimal(amount_raw)
    if amount.is_nan() or amount.is_infinite():
        raise ValidationError("Amount must be a finite numeric value.")
    if amount <= Decimal("0.00"):
        raise ValidationError("Amount must be positive.")
    if amount.as_tuple().exponent < -2:
        raise ValidationError("Amount cannot have more than 2 decimal places.")
    return amount


# ---------------------------------------------------------------------------
# Role enforcement helper
# ---------------------------------------------------------------------------

def _role_required(required_role: str):
    """
    Decorator factory: the decorated view is only accessible to authenticated
    users whose CBS Group matches *required_role*.  Returns HTTP 403 otherwise.
    """
    def decorator(view_func):
        @login_required(login_url='/login/')
        def wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            role = get_user_role(request.user)
            if role != required_role:
                return HttpResponseForbidden(
                    f"Access denied. This dashboard is for {required_role} users only."
                )
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# Dashboard views
# ---------------------------------------------------------------------------

@_role_required('Manager')
def manager_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Manager Dashboard — /dashboard/manager/

    Context:
    - user                 : authenticated User object
    - profile              : StaffProfile (may be None)
    - branch               : Branch linked to the profile (may be None)
    - pending_count        : number of pending transactions for the manager's branch
    - pending_transactions : queryset of pending transactions for the manager's branch
    """
    profile, branch = get_user_staff_info(request.user)

    if branch:
        pending_transactions = Transaction.objects.filter(
            account__branch=branch,
            authorization_status=Transaction.AuthorizationStatus.PENDING,
        ).select_related('account', 'created_by', 'account__customer').order_by('-created_at')
    elif request.user.is_superuser:
        pending_transactions = Transaction.objects.filter(
            authorization_status=Transaction.AuthorizationStatus.PENDING,
        ).select_related('account', 'created_by', 'account__customer').order_by('-created_at')
    else:
        pending_transactions = Transaction.objects.none()

    pending_count = pending_transactions.count()

    context = {
        'role': 'Manager',
        'user': request.user,
        'profile': profile,
        'branch': branch,
        'pending_count': pending_count,
        'pending_transactions': pending_transactions,
    }
    return render(request, 'users/dashboard_manager.html', context)


@_role_required('Manager')
def manager_approve_transaction(request: HttpRequest, transaction_id: int) -> HttpResponse:
    """
    Approve transaction endpoint for Manager Dashboard.
    Delegates to existing authorization_service.approve_transaction.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    transaction = get_object_or_404(Transaction, pk=transaction_id)
    profile, branch = get_user_staff_info(request.user)

    # Branch security check (unless superuser)
    if not request.user.is_superuser:
        if not branch or transaction.account.branch_id != branch.id:
            return HttpResponseForbidden("Access denied. You can only approve transactions for your own branch.")

    try:
        approve_transaction(transaction=transaction, checker_user=request.user)
        messages.success(request, f"Transaction {transaction.transaction_id} approved and posted successfully.")
    except ValidationError as e:
        err_msg = e.message if hasattr(e, 'message') else str(e)
        messages.error(request, f"Approval failed: {err_msg}")
    except Exception as e:
        messages.error(request, f"Approval failed: {str(e)}")

    return redirect('dashboard_manager')


@_role_required('Manager')
def manager_reject_transaction(request: HttpRequest, transaction_id: int) -> HttpResponse:
    """
    Reject transaction endpoint for Manager Dashboard.
    Delegates to existing authorization_service.reject_transaction with optional reason.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    transaction = get_object_or_404(Transaction, pk=transaction_id)
    profile, branch = get_user_staff_info(request.user)

    # Branch security check (unless superuser)
    if not request.user.is_superuser:
        if not branch or transaction.account.branch_id != branch.id:
            return HttpResponseForbidden("Access denied. You can only reject transactions for your own branch.")

    reason = request.POST.get('rejection_reason', '').strip() or request.POST.get('reason', '').strip()
    try:
        reject_transaction(transaction=transaction, checker_user=request.user, reason=reason)
        messages.success(request, f"Transaction {transaction.transaction_id} rejected successfully.")
    except ValidationError as e:
        err_msg = e.message if hasattr(e, 'message') else str(e)
        messages.error(request, f"Rejection failed: {err_msg}")
    except Exception as e:
        messages.error(request, f"Rejection failed: {str(e)}")

    return redirect('dashboard_manager')


@_role_required('Teller')
def teller_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Teller Dashboard — /dashboard/teller/

    Context:
    - user    : authenticated User object
    - profile : StaffProfile (may be None)
    - branch  : Branch linked to the profile (may be None)
    """
    profile, branch = get_user_staff_info(request.user)

    context = {
        'role': 'Teller',
        'user': request.user,
        'profile': profile,
        'branch': branch,
    }
    return render(request, 'users/dashboard_teller.html', context)


@_role_required('Teller')
def teller_deposit(request: HttpRequest) -> HttpResponse:
    """
    Teller Cash Deposit POST View — /dashboard/teller/deposit/
    Creates a PENDING cash deposit transaction requiring Manager approval.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    account_number = request.POST.get('account_number', '').strip()
    amount_raw = request.POST.get('amount', '').strip()
    description = request.POST.get('description', '').strip()

    if not account_number or not amount_raw:
        messages.error(request, "Account number and deposit amount are required.")
        return redirect('dashboard_teller')

    try:
        amount = Decimal(amount_raw)
    except (InvalidOperation, ValueError):
        messages.error(request, "Invalid deposit amount. Please enter a valid decimal number.")
        return redirect('dashboard_teller')

    try:
        account = Account.objects.get(account_number=account_number)
    except Account.DoesNotExist:
        messages.error(request, f"Account '{account_number}' not found.")
        return redirect('dashboard_teller')

    try:
        txn = deposit(
            account=account,
            amount=amount,
            created_by=request.user,
            description=description,
        )
        messages.success(
            request,
            f"Deposit transaction {txn.transaction_id} initiated successfully. "
            f"Status is PENDING and requires Manager approval."
        )
    except ValidationError as e:
        err_msg = e.message if hasattr(e, 'message') else str(e)
        if hasattr(e, 'message_dict') and isinstance(e.message_dict, dict):
            err_msg = "; ".join([f"{', '.join(v)}" for k, v in e.message_dict.items()])
        messages.error(request, f"Deposit failed: {err_msg}")
    except Exception as e:
        logger.error(f"Unexpected error during deposit: {str(e)}", exc_info=True)
        messages.error(request, "Deposit failed due to a server error. Please contact administrator.")

    return redirect('dashboard_teller')


@_role_required('Teller')
def teller_withdraw(request: HttpRequest) -> HttpResponse:
    """
    Teller Cash Withdrawal POST View — /dashboard/teller/withdraw/
    Creates a PENDING cash withdrawal transaction requiring Manager approval.
    """
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    account_number = request.POST.get('account_number', '').strip()
    amount_raw = request.POST.get('amount', '').strip()
    description = request.POST.get('description', '').strip()

    if not account_number or not amount_raw:
        messages.error(request, "Account number and withdrawal amount are required.")
        return redirect('dashboard_teller')

    try:
        amount = parse_decimal_amount(amount_raw)
    except (InvalidOperation, ValueError, ValidationError) as e:
        err_msg = str(e) if isinstance(e, ValidationError) else "Invalid withdrawal amount format."
        messages.error(request, f"Withdrawal failed: {err_msg}")
        return redirect('dashboard_teller')

    try:
        account = Account.objects.get(account_number=account_number)
    except Account.DoesNotExist:
        messages.error(request, f"Account '{account_number}' not found.")
        return redirect('dashboard_teller')

    try:
        txn = withdraw(
            account=account,
            amount=amount,
            created_by=request.user,
            description=description,
        )
        messages.success(
            request,
            f"Withdrawal transaction {txn.transaction_id} initiated successfully. "
            f"Status is PENDING and requires Manager approval."
        )
    except ValidationError as e:
        err_msg = e.message if hasattr(e, 'message') else str(e)
        if hasattr(e, 'message_dict') and isinstance(e.message_dict, dict):
            err_msg = "; ".join([f"{', '.join(v)}" for k, v in e.message_dict.items()])
        messages.error(request, f"Withdrawal failed: {err_msg}")
    except Exception as e:
        logger.error(f"Unexpected error during withdrawal: {str(e)}", exc_info=True)
        messages.error(request, "Withdrawal failed due to a server error. Please contact administrator.")

    return redirect('dashboard_teller')


@_role_required('Auditor')
def auditor_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Auditor Dashboard — /dashboard/auditor/

    Context:
    - user    : authenticated User object
    - profile : StaffProfile (may be None)
    - branch  : Branch linked to the profile (may be None)
    """
    profile, branch = get_user_staff_info(request.user)

    context = {
        'role': 'Auditor',
        'user': request.user,
        'profile': profile,
        'branch': branch,
    }
    return render(request, 'users/dashboard_auditor.html', context)
