import json
from datetime import date

from django.contrib.auth import authenticate, login as django_login
from django.db import DatabaseError, IntegrityError, transaction
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
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db.models import Q
from audit.models import AuditLog
from branches.models import Branch
from customers.models import Customer
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


def _admin_authorization_error(user):
    if not user.is_authenticated or not user.is_active:
        return JsonResponse(
            {"success": False, "message": "Authentication required"},
            status=401
        )

    if (
        not user.groups.filter(name="Admin").exists()
        or user.groups.filter(
            name__in=("Manager", "Teller", "Officer", "Auditor")
        ).exists()
    ):
        return JsonResponse(
            {"success": False, "message": "Admin access required"},
            status=403
        )

    return None


class _AuditLogWriteFailed(Exception):
    pass


_CUSTOMER_REGISTRATION_FIELDS = {
    "customer_type",
    "full_name",
    "phone",
    "email",
    "date_of_birth",
    "gender",
    "nid_number",
    "passport_number",
    "present_address",
    "permanent_address",
    "district",
    "home_branch",
    "nominee_name",
    "nominee_relationship",
    "nominee_phone",
}
_CUSTOMER_OPTIONAL_FIELDS = {
    "email",
    "date_of_birth",
    "gender",
    "nid_number",
    "passport_number",
    "permanent_address",
    "nominee_name",
    "nominee_relationship",
    "nominee_phone",
}
_CUSTOMER_FIELD_MAX_LENGTHS = {
    "customer_type": 20,
    "full_name": 150,
    "phone": 20,
    "email": 254,
    "gender": 10,
    "nid_number": 30,
    "passport_number": 30,
    "present_address": 5000,
    "permanent_address": 5000,
    "district": 100,
    "nominee_name": 150,
    "nominee_relationship": 50,
    "nominee_phone": 20,
}
_CUSTOMER_REQUIRED_FIELDS = {
    "full_name",
    "phone",
    "present_address",
    "district",
    "home_branch",
}
_MAX_CUSTOMER_REQUEST_BYTES = 16_384


def _customer_registration_error(message, *, errors=None, status_code=400):
    response = {"success": False, "message": message}
    if errors:
        response["errors"] = errors
    return JsonResponse(response, status=status_code)


def _parse_customer_registration(request):
    if request.content_type != "application/json":
        return None, _customer_registration_error(
            "Content-Type must be application/json."
        )

    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        try:
            if int(content_length) > _MAX_CUSTOMER_REQUEST_BYTES:
                return None, _customer_registration_error(
                    "Request body is too large.",
                    status_code=413,
                )
        except ValueError:
            return None, _customer_registration_error(
                "Invalid Content-Length header."
            )

    try:
        body = request.body
    except RequestDataTooBig:
        return None, _customer_registration_error(
            "Request body is too large.",
            status_code=413,
        )

    if len(body) > _MAX_CUSTOMER_REQUEST_BYTES:
        return None, _customer_registration_error(
            "Request body is too large.",
            status_code=413,
        )

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _customer_registration_error(
            "Request body must be valid JSON."
        )

    if not isinstance(payload, dict):
        return None, _customer_registration_error(
            "Request body must be a JSON object."
        )

    if payload.keys() - _CUSTOMER_REGISTRATION_FIELDS:
        return None, _customer_registration_error(
            "Request contains unsupported registration fields."
        )

    missing_fields = _CUSTOMER_REQUIRED_FIELDS - payload.keys()
    if missing_fields:
        return None, _customer_registration_error(
            "Required customer fields are missing.",
            errors={field: ["This field is required."] for field in sorted(missing_fields)},
        )

    normalized = {}
    for field, value in payload.items():
        if field == "home_branch":
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                return None, _customer_registration_error(
                    "Invalid registration field.",
                    errors={field: ["Enter a valid branch ID."]},
                )
            normalized[field] = value
            continue

        if field == "date_of_birth":
            if value is None and field in _CUSTOMER_OPTIONAL_FIELDS:
                normalized[field] = None
                continue
            if not isinstance(value, str):
                return None, _customer_registration_error(
                    "Invalid registration field.",
                    errors={field: ["Enter a date in YYYY-MM-DD format."]},
                )
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError:
                return None, _customer_registration_error(
                    "Invalid registration field.",
                    errors={field: ["Enter a valid date in YYYY-MM-DD format."]},
                )
            if parsed_date.isoformat() != value:
                return None, _customer_registration_error(
                    "Invalid registration field.",
                    errors={field: ["Enter a date in YYYY-MM-DD format."]},
                )
            normalized[field] = parsed_date
            continue

        if value is None and field in _CUSTOMER_OPTIONAL_FIELDS:
            normalized[field] = None
            continue
        if not isinstance(value, str):
            return None, _customer_registration_error(
                "Invalid registration field.",
                errors={field: ["Enter a valid text value."]},
            )

        if len(value) > _CUSTOMER_FIELD_MAX_LENGTHS[field]:
            return None, _customer_registration_error(
                "Invalid registration field.",
                errors={field: ["Value exceeds the maximum allowed length."]},
            )
        if field in {"nid_number", "passport_number"} and not value.strip():
            value = None
        normalized[field] = value

    return normalized, None


@require_GET
def admin_session_api(request):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    return JsonResponse({
        "success": True,
        "username": request.user.username,
        "role": "Admin"
    })


@csrf_protect
def admin_customers_api(request):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    if request.method == "POST":
        payload, error_response = _parse_customer_registration(request)
        if error_response:
            return error_response

        branch = Branch.objects.filter(
            pk=payload.pop("home_branch"),
            is_active=True,
        ).only("id", "branch_name").first()
        if branch is None:
            return _customer_registration_error(
                "Select an existing active branch.",
                errors={"home_branch": ["Select an existing active branch."]},
            )

        customer = Customer(
            **payload,
            home_branch=branch,
            created_by=request.user,
        )
        try:
            with transaction.atomic():
                customer.save()
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action="CREATE_CUSTOMER",
                        model_name="Customer",
                        object_id=str(customer.pk),
                        description="Customer registered through the Admin API.",
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                except DatabaseError as error:
                    raise _AuditLogWriteFailed from error
        except ValidationError as error:
            validation_fields = getattr(error, "message_dict", {})
            safe_errors = {
                field: ["Invalid or conflicting value."]
                for field in validation_fields
            }
            return _customer_registration_error(
                "Customer registration data is invalid.",
                errors=safe_errors,
            )
        except IntegrityError:
            return _customer_registration_error(
                "Customer registration conflicts with an existing record.",
                status_code=409,
            )
        except _AuditLogWriteFailed:
            return _customer_registration_error(
                "Customer registration could not be completed.",
                status_code=500,
            )

        return JsonResponse(
            {
                "success": True,
                "customer": {
                    "id": customer.pk,
                    "cif_number": customer.cif_number,
                    "full_name": customer.full_name,
                    "home_branch": branch.branch_name,
                    "kyc_status": customer.kyc_status,
                },
            },
            status=201,
        )

    if request.method != "GET":
        return JsonResponse(
            {"success": False, "message": "GET or POST method required."},
            status=405,
        )

    search = request.GET.get("search", "")
    if len(search) > 100:
        return JsonResponse(
            {
                "success": False,
                "message": "Search query must be 100 characters or fewer.",
            },
            status=400
        )

    customers = Customer.objects.all()
    search = search.strip()
    if search:
        customers = customers.filter(
            Q(full_name__icontains=search)
            | Q(cif_number__icontains=search)
            | Q(district__icontains=search)
            | Q(home_branch__branch_name__icontains=search)
        )

    customers = customers.select_related("home_branch").only(
        "id",
        "full_name",
        "customer_type",
        "kyc_status",
        "status",
        "created_at",
        "home_branch__branch_name",
    ).order_by("-created_at", "-id")
    paginator = Paginator(customers, 10)
    page_number = request.GET.get("page")
    try:
        if page_number is not None:
            page_number = max(1, int(page_number))
    except ValueError:
        pass
    page_obj = paginator.get_page(page_number)

    return JsonResponse({
        "success": True,
        "pagination": {
            "page": page_obj.number,
            "page_size": paginator.per_page,
            "total_pages": paginator.num_pages,
            "total_items": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
        "customers": [
            {
                "id": customer.pk,
                "full_name": customer.full_name,
                "customer_type": customer.customer_type,
                "kyc_status": customer.kyc_status,
                "status": customer.status,
                "home_branch": customer.home_branch.branch_name,
                "created_at": customer.created_at.isoformat(),
            }
            for customer in page_obj.object_list
        ],
    })


@require_GET
def admin_branch_options_api(request):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    branches = Branch.objects.filter(is_active=True).order_by(
        "branch_code",
        "id",
    ).only("id", "branch_code", "branch_name")
    return JsonResponse({
        "success": True,
        "branches": [
            {
                "id": branch.pk,
                "branch_code": branch.branch_code,
                "branch_name": branch.branch_name,
            }
            for branch in branches
        ],
    })


@require_GET
def teller_session_api(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required"},
            status=401
        )

    if get_user_role(request.user) != "Teller":
        return JsonResponse(
            {"success": False, "message": "Teller access required"},
            status=403
        )

    _, branch = get_user_staff_info(request.user)
    return JsonResponse({
        "success": True,
        "username": request.user.username,
        "role": "Teller",
        "branch": branch.branch_name if branch else None,
    })


@require_GET
def teller_transactions_api(request):
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Authentication required"},
            status=401
        )

    if get_user_role(request.user) != "Teller":
        return JsonResponse(
            {"success": False, "message": "Teller access required"},
            status=403
        )

    transactions = Transaction.objects.filter(created_by=request.user)

    account_number = request.GET.get("account_number", "").strip()
    transaction_type = request.GET.get("transaction_type", "").strip()
    transaction_status = request.GET.get("status", "").strip()
    if account_number:
        transactions = transactions.filter(account__account_number=account_number)
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    if transaction_status:
        transactions = transactions.filter(status=transaction_status)

    transactions = transactions.select_related("account").order_by(
        "-created_at",
        "-id",
    )
    paginator = Paginator(transactions, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    return JsonResponse({
        "success": True,
        "pagination": {
            "page": page_obj.number,
            "page_size": paginator.per_page,
            "total_pages": paginator.num_pages,
            "total_items": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
        "transactions": [
            {
                "id": transaction.pk,
                "transaction_id": transaction.transaction_id,
                "transaction_type": transaction.transaction_type,
                "account_number": transaction.account.account_number,
                "amount": str(transaction.amount),
                "status": transaction.status,
                "authorization_status": transaction.authorization_status,
                "created_at": transaction.created_at.isoformat(),
            }
            for transaction in page_obj.object_list
        ],
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