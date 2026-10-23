import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import authenticate, login as django_login
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
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
from accounts.models import Account
from products.models import AccountProduct
from transactions.models import Transaction
from users.models import StaffProfile
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


_ACCOUNT_OPENING_FIELDS = {"customer", "product", "branch"}
_MAX_ACCOUNT_REQUEST_BYTES = 1024


_BRANCH_CREATE_FIELDS = {
    "branch_code",
    "branch_name",
    "routing_number",
    "address",
    "district",
    "phone",
    "email",
}
_BRANCH_UPDATE_FIELDS = {
    "branch_name",
    "address",
    "district",
    "phone",
    "email",
    "is_active",
}
_BRANCH_REQUIRED_FIELDS = {
    "branch_code",
    "branch_name",
    "address",
    "district",
}
_BRANCH_MAX_LENGTHS = {
    "branch_code": 20,
    "branch_name": 150,
    "routing_number": 20,
    "district": 100,
    "phone": 20,
    "email": 254,
}
_MAX_BRANCH_REQUEST_BYTES = 16_384


class _BranchAuditWriteFailed(Exception):
    pass


def _branch_api_error(message, *, errors=None, status_code=400):
    response = {"success": False, "message": message}
    if errors:
        response["errors"] = errors
    return JsonResponse(response, status=status_code)


def _parse_branch_payload(request, *, create):
    if request.content_type != "application/json":
        return None, _branch_api_error(
            "Content-Type must be application/json."
        )

    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        try:
            if int(content_length) > _MAX_BRANCH_REQUEST_BYTES:
                return None, _branch_api_error(
                    "Request body is too large.",
                    status_code=413,
                )
        except ValueError:
            return None, _branch_api_error("Invalid Content-Length header.")

    try:
        body = request.body
    except RequestDataTooBig:
        return None, _branch_api_error(
            "Request body is too large.",
            status_code=413,
        )
    if len(body) > _MAX_BRANCH_REQUEST_BYTES:
        return None, _branch_api_error(
            "Request body is too large.",
            status_code=413,
        )

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _branch_api_error("Request body must be valid JSON.")
    if not isinstance(payload, dict):
        return None, _branch_api_error(
            "Request body must be a JSON object."
        )
    if not payload:
        return None, _branch_api_error("Request body must not be empty.")

    allowed_fields = _BRANCH_CREATE_FIELDS if create else _BRANCH_UPDATE_FIELDS
    unsupported_fields = payload.keys() - allowed_fields
    if unsupported_fields:
        immutable_fields = unsupported_fields & {"branch_code", "routing_number"}
        if not create and immutable_fields:
            return None, _branch_api_error(
                "Branch code and routing number cannot be changed."
            )
        return None, _branch_api_error(
            "Request contains unsupported branch fields."
        )

    if create:
        missing_fields = _BRANCH_REQUIRED_FIELDS - payload.keys()
        if missing_fields:
            return None, _branch_api_error(
                "Required branch fields are missing.",
                errors={
                    field: ["This field is required."]
                    for field in sorted(missing_fields)
                },
            )

    normalized = {}
    optional_fields = {"routing_number", "phone", "email"}
    for field, value in payload.items():
        if field == "is_active":
            if not isinstance(value, bool):
                return None, _branch_api_error(
                    "is_active must be a boolean.",
                    errors={field: ["Enter true or false."]},
                )
            normalized[field] = value
            continue

        if value is None and field in optional_fields:
            normalized[field] = None
            continue
        if not isinstance(value, str):
            return None, _branch_api_error(
                "Branch fields must be text values.",
                errors={field: ["Enter a valid text value."]},
            )

        if field in optional_fields and not value.strip():
            normalized[field] = None
            continue
        if field in {"branch_code", "branch_name", "address", "district"}:
            value = value.strip()
            if not value:
                return None, _branch_api_error(
                    "Required branch fields cannot be blank.",
                    errors={field: ["This field is required."]},
                )
        max_length = _BRANCH_MAX_LENGTHS.get(field)
        if max_length is not None and len(value) > max_length:
            return None, _branch_api_error(
                "Branch field exceeds the maximum allowed length.",
                errors={field: ["Value exceeds the maximum allowed length."]},
            )
        normalized[field] = value

    return normalized, None


def _branch_response(branch):
    return {
        "id": branch.pk,
        "branch_code": branch.branch_code,
        "branch_name": branch.branch_name,
        "district": branch.district,
        "address": branch.address,
        "phone": branch.phone,
        "email": branch.email,
        "is_active": branch.is_active,
        "created_at": branch.created_at.isoformat(),
        "updated_at": branch.updated_at.isoformat(),
    }


def _branch_validation_response(error):
    validation_fields = getattr(error, "message_dict", {})
    unique_fields = {"branch_code", "routing_number"}
    if unique_fields.intersection(validation_fields):
        return _branch_api_error(
            "Branch code or routing number already exists.",
            status_code=409,
        )
    safe_errors = {
        field: ["Invalid value."]
        for field in validation_fields
    }
    return _branch_api_error(
        "Branch data is invalid.",
        errors=safe_errors,
    )


@json_csrf_protect
def admin_branches_api(request):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    if request.method == "POST":
        payload, error_response = _parse_branch_payload(request, create=True)
        if error_response:
            return error_response

        branch = Branch(**payload)
        try:
            with transaction.atomic():
                branch.full_clean()
                branch.save()
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action="CREATE_BRANCH",
                        model_name="Branch",
                        object_id=str(branch.pk),
                        description=f"Branch {branch.branch_code} created.",
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                except DatabaseError as error:
                    raise _BranchAuditWriteFailed from error
        except ValidationError as error:
            return _branch_validation_response(error)
        except IntegrityError:
            return _branch_api_error(
                "Branch code or routing number already exists.",
                status_code=409,
            )
        except _BranchAuditWriteFailed:
            return _branch_api_error(
                "Branch could not be created.",
                status_code=500,
            )

        return JsonResponse(
            {"success": True, "branch": _branch_response(branch)},
            status=201,
        )

    if request.method != "GET":
        return _branch_api_error(
            "GET or POST method required.",
            status_code=405,
        )

    page_value = request.GET.get("page", "1")
    try:
        page_number = int(page_value)
        if page_number < 1:
            raise ValueError
    except (TypeError, ValueError):
        return _branch_api_error("Page must be a positive integer.")

    status_filter = request.GET.get("status", "active").lower()
    if status_filter not in {"active", "inactive", "all"}:
        return _branch_api_error(
            "Status must be active, inactive, or all."
        )

    branches = Branch.objects.all()
    if status_filter == "active":
        branches = branches.filter(is_active=True)
    elif status_filter == "inactive":
        branches = branches.filter(is_active=False)
    branches = branches.only(
        "id",
        "branch_code",
        "branch_name",
        "district",
        "address",
        "phone",
        "email",
        "is_active",
        "created_at",
        "updated_at",
    ).order_by("branch_code", "id")
    paginator = Paginator(branches, 10)
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
        "branches": [
            _branch_response(branch)
            for branch in page_obj.object_list
        ],
    })


@json_csrf_protect
def admin_branch_detail_api(request, branch_id):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    if request.method == "GET":
        branch = Branch.objects.filter(pk=branch_id).first()
        if branch is None:
            return _branch_api_error(
                "Branch not found.",
                status_code=404,
            )
        return JsonResponse({
            "success": True,
            "branch": _branch_response(branch),
        })

    if request.method != "PATCH":
        return _branch_api_error(
            "GET or PATCH method required.",
            status_code=405,
        )

    payload, error_response = _parse_branch_payload(request, create=False)
    if error_response:
        return error_response

    try:
        with transaction.atomic():
            branch = Branch.objects.select_for_update().filter(
                pk=branch_id
            ).first()
            if branch is None:
                return _branch_api_error(
                    "Branch not found.",
                    status_code=404,
                )

            was_active = branch.is_active
            for field, value in payload.items():
                setattr(branch, field, value)
            branch.full_clean()
            branch.save()

            if was_active and not branch.is_active:
                action = "DEACTIVATE_BRANCH"
                description = f"Branch {branch.branch_code} deactivated."
            elif not was_active and branch.is_active:
                action = "UPDATE_BRANCH"
                description = f"Branch {branch.branch_code} reactivated."
            else:
                action = "UPDATE_BRANCH"
                changed_fields = ", ".join(sorted(payload))
                description = (
                    f"Branch {branch.branch_code} updated "
                    f"(fields: {changed_fields})."
                )

            try:
                AuditLog.objects.create(
                    user=request.user,
                    action=action,
                    model_name="Branch",
                    object_id=str(branch.pk),
                    description=description,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
            except DatabaseError as error:
                raise _BranchAuditWriteFailed from error
    except ValidationError as error:
        return _branch_validation_response(error)
    except IntegrityError:
        return _branch_api_error(
            "Branch update conflicts with an existing record.",
            status_code=409,
        )
    except _BranchAuditWriteFailed:
        return _branch_api_error(
            "Branch update could not be completed.",
            status_code=500,
        )

    return JsonResponse({
        "success": True,
        "branch": _branch_response(branch),
    })


_STAFF_ROLES = ("Manager", "Officer", "Teller", "Auditor")
_STAFF_BANKING_ROLES = ("Admin", *_STAFF_ROLES)
_STAFF_CREATE_FIELDS = {
    "username",
    "password",
    "first_name",
    "last_name",
    "email",
    "employee_id",
    "branch",
    "designation",
    "phone",
    "role",
}
_STAFF_UPDATE_FIELDS = {
    "first_name",
    "last_name",
    "email",
    "designation",
    "phone",
    "branch",
    "role",
}
_STAFF_REQUIRED_CREATE_FIELDS = {
    "username",
    "password",
    "employee_id",
    "branch",
    "role",
}
_STAFF_FIELD_MAX_LENGTHS = {
    "username": 150,
    "password": 256,
    "first_name": 150,
    "last_name": 150,
    "email": 254,
    "employee_id": 30,
    "designation": 100,
    "phone": 20,
    "role": 20,
}
_MAX_STAFF_REQUEST_BYTES = 16_384


class _StaffAuditWriteFailed(Exception):
    pass


def _staff_api_error(message, *, errors=None, status_code=400):
    response = {"success": False, "message": message}
    if errors:
        response["errors"] = errors
    return JsonResponse(response, status=status_code)


def _parse_staff_payload(request, *, create):
    if request.content_type != "application/json":
        return None, _staff_api_error(
            "Content-Type must be application/json."
        )
    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        try:
            if int(content_length) > _MAX_STAFF_REQUEST_BYTES:
                return None, _staff_api_error(
                    "Request body is too large.",
                    status_code=413,
                )
        except ValueError:
            return None, _staff_api_error("Invalid Content-Length header.")

    try:
        body = request.body
    except RequestDataTooBig:
        return None, _staff_api_error(
            "Request body is too large.",
            status_code=413,
        )
    if len(body) > _MAX_STAFF_REQUEST_BYTES:
        return None, _staff_api_error(
            "Request body is too large.",
            status_code=413,
        )
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _staff_api_error("Request body must be valid JSON.")
    if not isinstance(payload, dict) or not payload:
        return None, _staff_api_error(
            "Request body must be a non-empty JSON object."
        )

    allowed_fields = _STAFF_CREATE_FIELDS if create else _STAFF_UPDATE_FIELDS
    if payload.keys() - allowed_fields:
        return None, _staff_api_error(
            "Request contains unsupported staff fields."
        )
    if create:
        missing = _STAFF_REQUIRED_CREATE_FIELDS - payload.keys()
        if missing:
            return None, _staff_api_error(
                "Required staff fields are missing.",
                errors={
                    field: ["This field is required."]
                    for field in sorted(missing)
                },
            )

    normalized = {}
    optional_text = {
        "first_name",
        "last_name",
        "email",
        "designation",
        "phone",
    }
    for field, value in payload.items():
        if field == "branch":
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                return None, _staff_api_error(
                    "Branch must be a valid database ID.",
                    errors={field: ["Select a valid branch."]},
                )
            normalized[field] = value
            continue
        if not isinstance(value, str):
            return None, _staff_api_error(
                "Staff fields must have valid types.",
                errors={field: ["Enter a valid value."]},
            )
        if field in optional_text and not value.strip():
            value = ""
        elif field in {"username", "employee_id", "role"}:
            value = value.strip()
            if not value:
                return None, _staff_api_error(
                    "Required staff fields cannot be blank.",
                    errors={field: ["This field is required."]},
                )
        if len(value) > _STAFF_FIELD_MAX_LENGTHS[field]:
            return None, _staff_api_error(
                "Staff field exceeds the maximum allowed length.",
                errors={field: ["Value exceeds the maximum allowed length."]},
            )
        normalized[field] = value

    if "role" in normalized and normalized["role"] not in _STAFF_ROLES:
        return None, _staff_api_error(
            "Select one approved non-Admin banking role.",
            errors={"role": ["Unsupported banking role."]},
        )
    return normalized, None


def _staff_banking_role(user):
    roles = set(user.groups.filter(name__in=_STAFF_ROLES).values_list(
        "name",
        flat=True,
    ))
    if len(roles) == 1 and not user.groups.filter(name="Admin").exists():
        return next(iter(roles))
    if not roles and not user.groups.filter(name="Admin").exists():
        return None
    return "CONFLICT"


def _staff_response(profile):
    user = profile.user
    branch = profile.branch
    return {
        "id": profile.pk,
        "employee_id": profile.employee_id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "designation": profile.designation,
        "phone": profile.phone,
        "branch": {
            "id": branch.pk,
            "branch_code": branch.branch_code,
            "branch_name": branch.branch_name,
        },
        "role": _staff_banking_role(user),
        "user_is_active": user.is_active,
        "profile_is_active": profile.is_active,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


def _get_managed_staff_queryset():
    return StaffProfile.objects.select_related("user", "branch").exclude(
        user__is_superuser=True,
    ).exclude(
        user__groups__name="Admin",
    ).distinct()


def _get_managed_staff_for_update(staff_id):
    profile = StaffProfile.objects.select_for_update().select_related(
        "user",
        "branch",
    ).filter(pk=staff_id).first()
    if (
        profile is None
        or profile.user.is_superuser
        or profile.user.groups.filter(name="Admin").exists()
    ):
        return None
    return profile


def _validate_staff_email(email):
    try:
        User._meta.get_field("email").clean(email, None)
    except ValidationError:
        return False
    return True


@json_csrf_protect
def admin_staff_api(request):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    if request.method == "POST":
        payload, error_response = _parse_staff_payload(request, create=True)
        if error_response:
            return error_response
        if not _validate_staff_email(payload.get("email", "")):
            return _staff_api_error(
                "Enter a valid email address.",
                errors={"email": ["Enter a valid email address."]},
            )

        try:
            branch = Branch.objects.get(
                pk=payload["branch"],
                is_active=True,
            )
        except Branch.DoesNotExist:
            return _staff_api_error(
                "Select an existing active branch.",
                errors={"branch": ["Select an existing active branch."]},
            )

        user = User(
            username=payload["username"],
            first_name=payload.get("first_name", ""),
            last_name=payload.get("last_name", ""),
            email=payload.get("email", ""),
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        try:
            User._meta.get_field("username").clean(user.username, user)
        except ValidationError:
            return _staff_api_error(
                "Username is invalid.",
                errors={"username": ["Enter a valid username."]},
            )
        try:
            validate_password(payload["password"], user=user)
        except ValidationError:
            return _staff_api_error(
                "Password does not meet the configured security requirements.",
                errors={"password": ["Choose a stronger password."]},
            )

        try:
            with transaction.atomic():
                branch = Branch.objects.select_for_update().get(
                    pk=payload["branch"],
                    is_active=True,
                )
                user = User.objects.create_user(
                    username=payload["username"],
                    password=payload["password"],
                    first_name=payload.get("first_name", ""),
                    last_name=payload.get("last_name", ""),
                    email=payload.get("email", ""),
                    is_active=True,
                    is_staff=False,
                    is_superuser=False,
                )
                profile = StaffProfile.objects.create(
                    user=user,
                    employee_id=payload["employee_id"],
                    branch=branch,
                    designation=payload.get("designation") or None,
                    phone=payload.get("phone") or None,
                    is_active=True,
                )
                role_group = Group.objects.get(name=payload["role"])
                user.groups.add(role_group)
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action="CREATE_STAFF",
                        model_name="StaffProfile",
                        object_id=str(profile.pk),
                        description=(
                            f"Staff profile created with role {payload['role']}."
                        ),
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                except DatabaseError as error:
                    raise _StaffAuditWriteFailed from error
        except Branch.DoesNotExist:
            return _staff_api_error(
                "Select an existing active branch.",
                errors={"branch": ["Select an existing active branch."]},
            )
        except Group.DoesNotExist:
            return _staff_api_error(
                "The selected banking role is not configured.",
                status_code=400,
            )
        except IntegrityError:
            return _staff_api_error(
                "Username or employee ID already exists.",
                status_code=409,
            )
        except _StaffAuditWriteFailed:
            return _staff_api_error(
                "Staff account could not be created.",
                status_code=500,
            )

        return JsonResponse(
            {"success": True, "staff": _staff_response(profile)},
            status=201,
        )

    if request.method != "GET":
        return _staff_api_error(
            "GET or POST method required.",
            status_code=405,
        )

    page_value = request.GET.get("page", "1")
    try:
        page_number = int(page_value)
        if page_number < 1:
            raise ValueError
    except (TypeError, ValueError):
        return _staff_api_error("Page must be a positive integer.")

    profiles = _get_managed_staff_queryset().only(
        "id",
        "employee_id",
        "designation",
        "phone",
        "is_active",
        "created_at",
        "updated_at",
        "user__id",
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "user__is_active",
        "branch__id",
        "branch__branch_code",
        "branch__branch_name",
    ).order_by("employee_id", "id")
    paginator = Paginator(profiles, 10)
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
        "staff": [
            _staff_response(profile)
            for profile in page_obj.object_list
        ],
    })


@json_csrf_protect
def admin_staff_detail_api(request, staff_id):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    if request.method == "GET":
        profile = _get_managed_staff_queryset().filter(pk=staff_id).first()
        if profile is None:
            return _staff_api_error("Staff member not found.", status_code=404)
        return JsonResponse({
            "success": True,
            "staff": _staff_response(profile),
        })

    if request.method != "PATCH":
        return _staff_api_error(
            "GET or PATCH method required.",
            status_code=405,
        )

    payload, error_response = _parse_staff_payload(request, create=False)
    if error_response:
        return error_response
    if "email" in payload and not _validate_staff_email(payload["email"]):
        return _staff_api_error(
            "Enter a valid email address.",
            errors={"email": ["Enter a valid email address."]},
        )
    if not any(field in payload for field in _STAFF_UPDATE_FIELDS):
        return _staff_api_error("At least one editable field is required.")

    try:
        with transaction.atomic():
            profile = _get_managed_staff_for_update(staff_id)
            if profile is None:
                return _staff_api_error(
                    "Staff member not found.",
                    status_code=404,
                )
            if "branch" in payload:
                try:
                    branch = Branch.objects.select_for_update().get(
                        pk=payload["branch"],
                        is_active=True,
                    )
                except Branch.DoesNotExist:
                    return _staff_api_error(
                        "Select an existing active branch.",
                        errors={"branch": ["Select an existing active branch."]},
                    )
                profile.branch = branch

            role = payload.get("role")
            previous_role = _staff_banking_role(profile.user)
            if role:
                groups = set(profile.user.groups.values_list("name", flat=True))
                banking_groups = groups.intersection(_STAFF_BANKING_ROLES)
                unexpected_groups = groups - banking_groups
                if unexpected_groups:
                    return _staff_api_error(
                        "Staff with additional group memberships cannot have their role changed."
                    )
                if previous_role != role:
                    role_group = Group.objects.filter(name=role).first()
                    if role_group is None:
                        return _staff_api_error(
                            "The selected banking role is not configured."
                        )
                    profile.user.groups.remove(
                        *Group.objects.filter(name__in=_STAFF_BANKING_ROLES)
                    )
                    profile.user.groups.add(role_group)

            user_fields = []
            for field in ("first_name", "last_name", "email"):
                if field in payload:
                    setattr(profile.user, field, payload[field])
                    user_fields.append(field)
            if user_fields:
                profile.user.save(update_fields=user_fields)

            for field in ("designation", "phone"):
                if field in payload:
                    setattr(profile, field, payload[field] or None)
            profile.full_clean()
            profile.save()

            changed_profile_fields = sorted(
                set(payload).intersection({
                    "branch",
                    "designation",
                    "phone",
                })
            )
            if user_fields or changed_profile_fields:
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action="UPDATE_STAFF",
                        model_name="StaffProfile",
                        object_id=str(profile.pk),
                        description=(
                            "Staff profile updated "
                            f"(fields: {', '.join(sorted(user_fields + changed_profile_fields))})."
                        ),
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                except DatabaseError as error:
                    raise _StaffAuditWriteFailed from error

            if role and previous_role != role:
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action="CHANGE_STAFF_ROLE",
                        model_name="StaffProfile",
                        object_id=str(profile.pk),
                        description=f"Staff banking role changed to {role}.",
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                except DatabaseError as error:
                    raise _StaffAuditWriteFailed from error
    except ValidationError:
        return _staff_api_error("Staff profile data is invalid.")
    except IntegrityError:
        return _staff_api_error(
            "Staff update conflicts with an existing record.",
            status_code=409,
        )
    except _StaffAuditWriteFailed:
        return _staff_api_error(
            "Staff update could not be completed.",
            status_code=500,
        )

    return JsonResponse({
        "success": True,
        "staff": _staff_response(profile),
    })


@json_csrf_protect
def admin_staff_status_api(request, staff_id, action):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error
    if request.method != "POST":
        return _staff_api_error("POST method required.", status_code=405)

    if action not in {"activate", "deactivate"}:
        return _staff_api_error("Unsupported staff status action.")

    try:
        with transaction.atomic():
            profile = _get_managed_staff_for_update(staff_id)
            if profile is None:
                return _staff_api_error(
                    "Staff member not found.",
                    status_code=404,
                )
            if action == "activate":
                branch = Branch.objects.select_for_update().filter(
                    pk=profile.branch_id,
                    is_active=True,
                ).first()
                if branch is None:
                    return _staff_api_error(
                        "Staff cannot be activated while their branch is inactive."
                    )
                if _staff_banking_role(profile.user) not in _STAFF_ROLES:
                    return _staff_api_error(
                        "Staff must have exactly one approved banking role before activation."
                    )

            is_active = action == "activate"
            profile.user.is_active = is_active
            profile.is_active = is_active
            profile.user.save(update_fields=["is_active"])
            profile.save(update_fields=["is_active", "updated_at"])
            try:
                AuditLog.objects.create(
                    user=request.user,
                    action="ACTIVATE_STAFF" if is_active else "DEACTIVATE_STAFF",
                    model_name="StaffProfile",
                    object_id=str(profile.pk),
                    description=(
                        f"Staff profile {'activated' if is_active else 'deactivated'}."
                    ),
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
            except DatabaseError as error:
                raise _StaffAuditWriteFailed from error
    except _StaffAuditWriteFailed:
        return _staff_api_error(
            "Staff status could not be changed.",
            status_code=500,
        )

    return JsonResponse({
        "success": True,
        "staff": _staff_response(profile),
    })


def _account_api_error(message, *, status_code=400):
    return JsonResponse(
        {"success": False, "message": message},
        status=status_code,
    )


def _parse_account_opening(request):
    if request.content_type != "application/json":
        return None, _account_api_error(
            "Content-Type must be application/json."
        )

    content_length = request.META.get("CONTENT_LENGTH")
    if content_length:
        try:
            if int(content_length) > _MAX_ACCOUNT_REQUEST_BYTES:
                return None, _account_api_error(
                    "Request body is too large.",
                    status_code=413,
                )
        except ValueError:
            return None, _account_api_error("Invalid Content-Length header.")

    try:
        body = request.body
    except RequestDataTooBig:
        return None, _account_api_error(
            "Request body is too large.",
            status_code=413,
        )

    if len(body) > _MAX_ACCOUNT_REQUEST_BYTES:
        return None, _account_api_error(
            "Request body is too large.",
            status_code=413,
        )

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _account_api_error("Request body must be valid JSON.")

    if not isinstance(payload, dict):
        return None, _account_api_error(
            "Request body must be a JSON object."
        )
    if payload.keys() - _ACCOUNT_OPENING_FIELDS:
        return None, _account_api_error(
            "Request contains unsupported account-opening fields."
        )
    if payload.keys() != _ACCOUNT_OPENING_FIELDS:
        return None, _account_api_error(
            "Customer, product, and branch IDs are required."
        )

    for field, value in payload.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return None, _account_api_error(
                f"{field.capitalize()} must be a valid database ID."
            )

    return payload, None


class _AccountAuditWriteFailed(Exception):
    pass


@csrf_protect
def admin_accounts_api(request):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    if request.method == "POST":
        payload, error_response = _parse_account_opening(request)
        if error_response:
            return error_response

        try:
            with transaction.atomic():
                try:
                    customer = Customer.objects.select_for_update().get(
                        pk=payload["customer"]
                    )
                except Customer.DoesNotExist:
                    return _account_api_error(
                        "Select an existing active customer."
                    )

                try:
                    product = AccountProduct.objects.select_for_update().get(
                        pk=payload["product"]
                    )
                except AccountProduct.DoesNotExist:
                    return _account_api_error(
                        "Select an existing active account product."
                    )

                try:
                    branch = Branch.objects.select_for_update().get(
                        pk=payload["branch"]
                    )
                except Branch.DoesNotExist:
                    return _account_api_error(
                        "Select an existing active branch."
                    )

                if customer.status != Customer.Status.ACTIVE:
                    return _account_api_error(
                        "Select an existing active customer."
                    )
                if not product.is_active:
                    return _account_api_error(
                        "Select an existing active account product."
                    )
                if not branch.is_active:
                    return _account_api_error(
                        "Select an existing active branch."
                    )
                if customer.home_branch_id != branch.pk:
                    return _account_api_error(
                        "The account branch must match the customer's home branch."
                    )

                account = Account(
                    customer=customer,
                    product=product,
                    branch=branch,
                    currency=product.currency,
                    available_balance=Decimal("0.00"),
                    ledger_balance=Decimal("0.00"),
                    account_status=Account.AccountStatus.ACTIVE,
                )
                try:
                    account.save()
                except ValidationError as error:
                    if "account_number" in getattr(error, "message_dict", {}):
                        return _account_api_error(
                            "Account opening conflicts with an existing record.",
                            status_code=409,
                        )
                    return _account_api_error(
                        "The selected customer, product, or branch is not eligible for account opening."
                    )

                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action="CREATE_ACCOUNT",
                        model_name="Account",
                        object_id=str(account.pk),
                        description=(
                            f"Opened account {account.account_number} "
                            f"for customer {customer.cif_number}."
                        ),
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                except DatabaseError as error:
                    raise _AccountAuditWriteFailed from error
        except IntegrityError:
            return _account_api_error(
                "Account opening conflicts with an existing record.",
                status_code=409,
            )
        except _AccountAuditWriteFailed:
            return _account_api_error(
                "Account opening could not be completed.",
                status_code=500,
            )

        return JsonResponse(
            {
                "success": True,
                "account": {
                    "id": account.pk,
                    "account_number": account.account_number,
                    "customer_name": customer.full_name,
                    "customer_cif": customer.cif_number,
                    "product_code": product.product_code,
                    "product_name": product.product_name,
                    "branch_code": branch.branch_code,
                    "branch_name": branch.branch_name,
                    "currency": account.currency,
                    "account_status": account.account_status,
                    "opening_date": account.opening_date.isoformat(),
                    "available_balance": "0.00",
                    "ledger_balance": "0.00",
                },
            },
            status=201,
        )

    if request.method != "GET":
        return _account_api_error(
            "GET or POST method required.",
            status_code=405,
        )

    page_value = request.GET.get("page", "1")
    try:
        page_number = int(page_value)
        if page_number < 1:
            raise ValueError
    except (TypeError, ValueError):
        return _account_api_error(
            "Page must be a positive integer."
        )

    accounts = Account.objects.select_related(
        "customer",
        "product",
        "branch",
    ).only(
        "id",
        "account_number",
        "customer__full_name",
        "customer__cif_number",
        "product__product_code",
        "product__product_name",
        "branch__branch_code",
        "branch__branch_name",
        "currency",
        "account_status",
        "opening_date",
    ).order_by("account_number", "id")
    paginator = Paginator(accounts, 10)
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
        "accounts": [
            {
                "id": account.pk,
                "account_number": account.account_number,
                "customer_name": account.customer.full_name,
                "customer_cif": account.customer.cif_number,
                "product_code": account.product.product_code,
                "product_name": account.product.product_name,
                "branch_code": account.branch.branch_code,
                "branch_name": account.branch.branch_name,
                "currency": account.currency,
                "account_status": account.account_status,
                "opening_date": account.opening_date.isoformat(),
            }
            for account in page_obj.object_list
        ],
    })


@require_GET
def admin_account_customer_options_api(request):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    customers = Customer.objects.filter(
        status=Customer.Status.ACTIVE,
        home_branch__is_active=True,
    ).select_related("home_branch").only(
        "id",
        "cif_number",
        "full_name",
        "home_branch__id",
        "home_branch__branch_code",
        "home_branch__branch_name",
    ).order_by("full_name", "id")

    return JsonResponse({
        "success": True,
        "customers": [
            {
                "id": customer.pk,
                "cif": customer.cif_number,
                "display_name": customer.full_name,
                "home_branch": {
                    "id": customer.home_branch_id,
                    "branch_code": customer.home_branch.branch_code,
                    "branch_name": customer.home_branch.branch_name,
                },
            }
            for customer in customers
        ],
    })


@require_GET
def admin_account_product_options_api(request):
    authorization_error = _admin_authorization_error(request.user)
    if authorization_error:
        return authorization_error

    products = AccountProduct.objects.filter(is_active=True).only(
        "id",
        "product_code",
        "product_name",
        "product_type",
        "currency",
    ).order_by("product_code", "id")

    return JsonResponse({
        "success": True,
        "products": [
            {
                "id": product.pk,
                "product_code": product.product_code,
                "product_name": product.product_name,
                "product_type": product.product_type,
                "currency": product.currency,
            }
            for product in products
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