from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission, IsAuthenticated
from django.core.exceptions import ValidationError
from accounts.models import Account
from transactions.models import Transaction
from transactions.serializers import DepositSerializer, WithdrawSerializer, TransferSerializer
from transactions.services.deposit_service import deposit
from transactions.services.withdrawal_service import withdraw
from transactions.services.transfer_service import transfer
from transactions.services.authorization_service import approve_transaction, reject_transaction
from users.views import get_user_role


class IsTeller(BasePermission):
    message = "Teller access required."

    def has_permission(self, request, view):
        return get_user_role(request.user) == "Teller"


def _validation_error_response(error):
    message = "; ".join(error.messages)
    error_fields = getattr(error, "message_dict", {})
    response_status = (
        status.HTTP_403_FORBIDDEN
        if "created_by" in error_fields
        else status.HTTP_400_BAD_REQUEST
    )
    return Response(
        {"success": False, "message": message},
        status=response_status,
    )


def _serializer_error_response(serializer):
    return Response(
        {
            "success": False,
            "message": "Request validation failed.",
            "errors": serializer.errors,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


class TellerOperationAPIView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated, IsTeller]

    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if response is not None and "detail" in response.data:
            response.data = {
                "success": False,
                "message": str(response.data["detail"]),
            }
        return response


class DepositAPIView(TellerOperationAPIView):

    def post(self, request, *args, **kwargs):
        serializer = DepositSerializer(data=request.data)
        if not serializer.is_valid():
            return _serializer_error_response(serializer)

        account = Account.objects.get(
            account_number=serializer.validated_data['account_number']
        )
        try:
            txn = deposit(
                account=account,
                amount=serializer.validated_data['amount'],
                created_by=request.user,
                description=serializer.validated_data.get('description', ''),
            )
        except ValidationError as error:
            return _validation_error_response(error)

        account.refresh_from_db()
        return Response({
            "success": True,
            "message": "Deposit request submitted and pending Manager approval.",
            "transaction_id": txn.transaction_id,
            "account_number": account.account_number,
            "status": txn.status,
            "authorization_status": txn.authorization_status,
            "available_balance": str(account.available_balance),
            "ledger_balance": str(account.ledger_balance),
        }, status=status.HTTP_201_CREATED)


class WithdrawAPIView(TellerOperationAPIView):

    def post(self, request, *args, **kwargs):
        serializer = WithdrawSerializer(data=request.data)
        if not serializer.is_valid():
            return _serializer_error_response(serializer)

        account = Account.objects.get(
            account_number=serializer.validated_data['account_number']
        )
        try:
            txn = withdraw(
                account=account,
                amount=serializer.validated_data['amount'],
                created_by=request.user,
                description=serializer.validated_data.get('description', ''),
            )
        except ValidationError as error:
            return _validation_error_response(error)

        account.refresh_from_db()
        return Response({
            "success": True,
            "message": "Withdrawal request submitted and pending Manager approval.",
            "transaction_id": txn.transaction_id,
            "account_number": account.account_number,
            "status": txn.status,
            "authorization_status": txn.authorization_status,
            "available_balance": str(account.available_balance),
            "ledger_balance": str(account.ledger_balance),
        }, status=status.HTTP_201_CREATED)


class TransferAPIView(TellerOperationAPIView):

    def post(self, request, *args, **kwargs):
        serializer = TransferSerializer(data=request.data)
        if not serializer.is_valid():
            return _serializer_error_response(serializer)

        from_account = Account.objects.get(
            account_number=serializer.validated_data['from_account_number']
        )
        to_account = Account.objects.get(
            account_number=serializer.validated_data['to_account_number']
        )
        try:
            txn = transfer(
                from_account=from_account,
                to_account=to_account,
                amount=serializer.validated_data['amount'],
                created_by=request.user,
                description=serializer.validated_data.get('description', ''),
            )
        except ValidationError as error:
            return _validation_error_response(error)

        from_account.refresh_from_db()
        to_account.refresh_from_db()
        return Response({
            "success": True,
            "message": "Transfer request submitted and pending Manager approval.",
            "transaction_id": txn.transaction_id,
            "from_account_number": from_account.account_number,
            "to_account_number": to_account.account_number,
            "status": txn.status,
            "authorization_status": txn.authorization_status,
            "from_available_balance": str(from_account.available_balance),
            "to_available_balance": str(to_account.available_balance),
        }, status=status.HTTP_201_CREATED)


class ApproveTransactionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        try:
            txn = Transaction.objects.get(pk=pk)
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            updated_txn = approve_transaction(transaction=txn, checker_user=request.user)
            return Response({
                "message": "Transaction approved successfully.",
                "transaction_id": updated_txn.transaction_id,
                "authorization_status": updated_txn.authorization_status,
                "approved_by": updated_txn.approved_by.username,
                "approved_at": updated_txn.approved_at.isoformat(),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RejectTransactionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        try:
            txn = Transaction.objects.get(pk=pk)
        except Transaction.DoesNotExist:
            return Response({"error": "Transaction not found."}, status=status.HTTP_404_NOT_FOUND)

        reason = request.data.get('reason', '')
        try:
            updated_txn = reject_transaction(transaction=txn, checker_user=request.user, reason=reason)
            return Response({
                "message": "Transaction rejected successfully.",
                "transaction_id": updated_txn.transaction_id,
                "authorization_status": updated_txn.authorization_status,
                "rejection_reason": updated_txn.rejection_reason,
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
