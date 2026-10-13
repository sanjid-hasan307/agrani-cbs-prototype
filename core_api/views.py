from django.contrib.auth import authenticate, login as django_login
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import LoginSerializer
from users.views import get_user_role, get_user_staff_info
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET
from django.core.paginator import Paginator
from transactions.models import Transaction

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