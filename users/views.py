"""
Custom CBS Authentication Views

Provides custom login and logout views for bank staff, with role detection
and role-based placeholder redirects.
"""
from typing import Optional, Tuple
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from branches.models import Branch
from users.models import StaffProfile


ROLE_REDIRECTS = {
    'Teller': '/dashboard/teller/',
    'Manager': '/dashboard/manager/',
    'Auditor': '/dashboard/auditor/',
    'Officer': '/dashboard/officer/',
    'Admin': '/dashboard/admin/',
}


def get_user_role(user: Optional[User]) -> Optional[str]:
    """
    Detects the primary banking role for a user from their assigned Groups.
    Priority order: Manager, Teller, Auditor, Officer, Admin.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    group_names = set(user.groups.values_list('name', flat=True))
    for role in ['Manager', 'Teller', 'Auditor', 'Officer', 'Admin']:
        if role in group_names:
            return role

    if getattr(user, 'is_superuser', False):
        return 'Admin'

    return None


def get_user_staff_info(user: Optional[User]) -> Tuple[Optional[StaffProfile], Optional[Branch]]:
    """
    Retrieves the StaffProfile and assigned Branch for an authenticated user.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None, None

    try:
        profile = getattr(user, 'staff_profile', None)
        branch = profile.branch if profile and profile.branch else None
        return profile, branch
    except Exception:
        return None, None


def get_role_redirect_url(user: User) -> str:
    """
    Returns the placeholder dashboard URL based on the detected user role.
    """
    role = get_user_role(user)
    return ROLE_REDIRECTS.get(role, '/dashboard/')


def login_view(request: HttpRequest) -> HttpResponse:
    """
    Custom CBS Login View for bank employees.
    Authenticates staff, detects role & branch, and redirects to appropriate dashboard.
    """
    if request.user.is_authenticated:
        return redirect(get_role_redirect_url(request.user))

    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not username or not password:
            error = "Please provide both username and password."
        else:
            # Explicit check for inactive user
            try:
                existing_user = User.objects.get(username=username)
                if not existing_user.is_active:
                    error = "Your account is inactive. Please contact administrator."
            except User.DoesNotExist:
                pass

            if not error:
                user = authenticate(request, username=username, password=password)
                if user is not None:
                    if not user.is_active:
                        error = "Your account is inactive. Please contact administrator."
                    else:
                        login(request, user)
                        # Detect user's role and StaffProfile/branch
                        role = get_user_role(user)
                        profile, branch = get_user_staff_info(user)

                        # Redirect to role-specific placeholder dashboard
                        redirect_url = get_role_redirect_url(user)
                        return redirect(redirect_url)
                else:
                    error = "Invalid username or password."

        if error:
            messages.error(request, error)

    return render(request, 'users/login.html', {'error': error})


def logout_view(request: HttpRequest) -> HttpResponseRedirect:
    """
    Custom CBS Logout View.
    Terminates user session and redirects to login page.
    """
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')
