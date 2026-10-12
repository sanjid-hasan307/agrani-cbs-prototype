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