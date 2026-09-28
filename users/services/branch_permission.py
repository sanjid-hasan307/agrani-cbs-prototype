"""
Branch Permission Helper Service

Provides reusable helpers to evaluate branch-based permissions and access control.
"""
from typing import Optional
from django.contrib.auth.models import User
from branches.models import Branch
from accounts.models import Account
from transactions.models import Transaction


def get_user_branch(user: Optional[User]) -> Optional[Branch]:
    """
    Returns the user's assigned Branch safely.

    Handles:
    - user is None or not authenticated: returns None
    - inactive user: returns None
    - missing StaffProfile (e.g. superuser or user without profile): returns None
    - inactive staff profile or inactive branch: returns None
    - valid active staff: returns assigned Branch
    """
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return None

    try:
        profile = getattr(user, 'staff_profile', None)
        if profile and profile.is_active and profile.branch and profile.branch.is_active:
            return profile.branch
    except Exception:
        return None

    return None


def can_access_account(user: Optional[User], account: Optional[Account]) -> bool:
    """
    Determines if the user has branch-level permission to access/operate on the account.

    Rules:
    - Superusers can access all accounts.
    - Unauthenticated/inactive users cannot access any account.
    - Active staff members can only access accounts belonging to their assigned branch.
    """
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return False

    if getattr(user, 'is_superuser', False):
        return True

    if not account:
        return False

    user_branch = get_user_branch(user)
    if not user_branch:
        return False

    account_branch = getattr(account, 'branch', None)
    return user_branch == account_branch


def can_approve_transaction(user: Optional[User], transaction: Optional[Transaction]) -> bool:
    """
    Determines if the user can approve a transaction based on role and branch ownership.

    Rules:
    - Superusers have global approval authority.
    - Unauthenticated/inactive users cannot approve transactions.
    - User must belong to the 'Manager' group.
    - User's branch must match the transaction account's branch.
    - Maker-checker verification (maker != checker) remains separate in the authorization service.
    """
    if not user or not getattr(user, 'is_authenticated', False) or not user.is_active:
        return False

    if getattr(user, 'is_superuser', False):
        return True

    if not transaction or not getattr(transaction, 'account', None):
        return False

    # Check manager role
    if not user.groups.filter(name='Manager').exists():
        return False

    # Check branch match with transaction account
    user_branch = get_user_branch(user)
    if not user_branch:
        return False

    account_branch = getattr(transaction.account, 'branch', None)
    return user_branch == account_branch
