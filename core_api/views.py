import json

from django.contrib.auth import authenticate, login as django_login
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import LoginSerializer
from users.views import get_user_role, get_user_staff_info
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.decorators import decorator_from_middleware, method_decorator
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from transactions.models import Transaction
from transactions.services.authorization_service import (
    approve_transaction,
    reject_transaction,
)


class _JsonCsrfViewMiddleware(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return JsonResponse(
            {"success": False, "message": "CSRF verification failed."},
            status=403,
        )


def json_csrf_protect(view_func):
    protected_view = decorator_from_middleware(_JsonCsrfViewMiddleware)(view_func)
    # Let the local middleware return JSON instead of the global HTML CSRF page.
    return csrf_exempt(protected_view)


@csrf_protect
@ensure_csrf_cookie
@api_view(['POST'])
def login_api(request):

    serializer = LoginSerializer(
        data=request.data
    )

    if not serializer.is_valid():
        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


    username = serializer.validated_data['username']
    password = serializer.validated_data['password']
    
    user = authenticate(
        username=username,
        password=password
    )


    if user is None:
        return Response(
            {
                "success": False,
                "message": "Invalid credentials"
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    django_login(request, user)
    # Determine the banking role from Django Groups
    role = get_user_role(user)

    # Get staff profile and branch information
    profile, branch = get_user_staff_info(user)


    return Response(
        {
            "success": True,
            "username": user.username,
            "role": role,
            "branch": branch.branch_name if branch else None
        },
        status=status.HTTP_200_OK
    )
@ensure_csrf_cookie
def csrf_api(request):
    return JsonResponse({"success": True})
@require_GET
def manager_session_api(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required"},
            status=401
        )

    if get_user_role(request.user) != "Manager":
        return JsonResponse(
            {"success": False, "message": "Manager access required"},
            status=403
        )

    return JsonResponse({
        "success": True,
        "username": request.user.username,
        "role": "Manager"
    })


@require_GET
def manager_pending_transactions_api(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required"},
            status=401
        )

    if get_user_role(request.user) != "Manager":
        return JsonResponse(
            {"success": False, "message": "Manager access required"},
            status=403
        )

    _, branch = get_user_staff_info(request.user)
    if branch:
        pending_transactions = Transaction.objects.filter(
            account__branch=branch,
            authorization_status=Transaction.AuthorizationStatus.PENDING,
        )
    elif request.user.is_superuser:
        pending_transactions = Transaction.objects.filter(
            authorization_status=Transaction.AuthorizationStatus.PENDING,
        )
    else:
        pending_transactions = Transaction.objects.none()

    account_number = request.GET.get("account_number", "").strip()
    transaction_type = request.GET.get("transaction_type", "").strip()
    if account_number:
        pending_transactions = pending_transactions.filter(
            account__account_number__icontains=account_number
        )
    if transaction_type:
        pending_transactions = pending_transactions.filter(
            transaction_type=transaction_type
        )

    pending_transactions = pending_transactions.select_related(
        "account", "created_by"
    ).order_by("-created_at")
    paginator = Paginator(pending_transactions, 10)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    transactions = [
        {   
            "id": transaction.pk,
            "transaction_id": transaction.transaction_id,
            "transaction_type": transaction.transaction_type,
            "account_number": transaction.account.account_number,
            "amount": str(transaction.amount),
            "status": transaction.status,
            "authorization_status": transaction.authorization_status,
            "created_by": transaction.created_by.username,
            "created_at": transaction.created_at.isoformat(),
        }
        for transaction in page_obj.object_list
    ]

    return JsonResponse({
        "pending_count": paginator.count,
        "pagination": {
            "page": page_obj.number,
            "page_size": paginator.per_page,
            "total_pages": paginator.num_pages,
            "total_items": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
        "transactions": transactions,
    })


def _manager_transaction_action(request, transaction_id, action, reason=""):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required."},
            status=401,
        )

    if not request.user.groups.filter(name="Manager").exists():
        return JsonResponse(
            {"success": False, "message": "Manager access required."},
            status=403,
        )

    transaction = Transaction.objects.select_related("account", "created_by").filter(
        pk=transaction_id
    ).first()
    if transaction is None:
        return JsonResponse(
            {"success": False, "message": "Transaction not found."},
            status=404,
        )

    _, branch = get_user_staff_info(request.user)
    if not request.user.is_superuser and (
        branch is None or transaction.account.branch_id != branch.id
    ):
        return JsonResponse(
            {"success": False, "message": "Access denied for this transaction."},
            status=403,
        )

    try:
        if action == "approve":
            approve_transaction(transaction=transaction, checker_user=request.user)
        else:
            reject_transaction(
                transaction=transaction,
                checker_user=request.user,
                reason=reason,
            )
    except ValidationError as error:
        validation_messages = error.messages
        past_action = "approved" if action == "approve" else "rejected"
        if any("Maker cannot" in message for message in validation_messages):
            message = "You cannot act on a transaction you created."
        elif any("Only PENDING transactions" in message for message in validation_messages):
            message = "Only pending transactions can be processed."
        else:
            message = f"Transaction could not be {past_action}."
        return JsonResponse(
            {"success": False, "message": message},
            status=400,
        )

    past_action = "approved" if action == "approve" else "rejected"
    return JsonResponse(
        {"success": True, "message": f"Transaction {past_action} successfully."},
        status=200,
    )


@json_csrf_protect
def manager_approve_transaction_api(request, transaction_id):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "POST method required."},
            status=405,
        )

    return _manager_transaction_action(request, transaction_id, "approve")


@json_csrf_protect
def manager_reject_transaction_api(request, transaction_id):
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "POST method required."},
            status=405,
        )

    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {"success": False, "message": "Request body must be valid JSON."},
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {"success": False, "message": "Request body must be a JSON object."},
            status=400,
        )

    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        return JsonResponse(
            {"success": False, "message": "Reason must be a string."},
            status=400,
        )
    if len(reason) > 500:
        return JsonResponse(
            {"success": False, "message": "Reason must be 500 characters or fewer."},
            status=400,
        )

    return _manager_transaction_action(
        request,
        transaction_id,
        "reject",
        reason=reason.strip(),
    )