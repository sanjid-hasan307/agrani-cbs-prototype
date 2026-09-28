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
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import render

from transactions.models import Transaction
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
    - user          : authenticated User object
    - profile       : StaffProfile (may be None)
    - branch        : Branch linked to the profile (may be None)
    - pending_count : number of transactions with status PENDING
    """
    profile, branch = get_user_staff_info(request.user)
    pending_count = Transaction.objects.filter(status=Transaction.Status.PENDING).count()

    context = {
        'role': 'Manager',
        'user': request.user,
        'profile': profile,
        'branch': branch,
        'pending_count': pending_count,
    }
    return render(request, 'users/dashboard_manager.html', context)


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
