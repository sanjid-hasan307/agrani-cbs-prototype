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
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render

from transactions.models import Transaction
from transactions.services.authorization_service import approve_transaction, reject_transaction
from users.views import get_user_role, get_user_staff_info


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
