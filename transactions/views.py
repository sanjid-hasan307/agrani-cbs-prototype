from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from accounts.models import Account
from transactions.models import Transaction
from transactions.serializers import DepositSerializer, WithdrawSerializer, TransferSerializer
from transactions.services.deposit_service import deposit
from transactions.services.withdrawal_service import withdraw
from transactions.services.transfer_service import transfer
from transactions.services.authorization_service import approve_transaction, reject_transaction


class DepositAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = DepositSerializer(data=request.data)
        if serializer.is_valid():
            account = Account.objects.get(account_number=serializer.validated_data['account_number'])
            amount = serializer.validated_data['amount']
            description = serializer.validated_data.get('description', '')

            try:
                txn = deposit(
                    account=account,
                    amount=amount,
                    created_by=request.user,
                    description=description,
                )
                account.refresh_from_db()
                return Response({
                    "message": "Deposit successful.",
                    "transaction_id": txn.transaction_id,
                    "account_number": account.account_number,
                    "available_balance": str(account.available_balance),
                    "ledger_balance": str(account.ledger_balance),
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class WithdrawAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = WithdrawSerializer(data=request.data)
        if serializer.is_valid():
            account = Account.objects.get(account_number=serializer.validated_data['account_number'])
            amount = serializer.validated_data['amount']
            description = serializer.validated_data.get('description', '')

            try:
                txn = withdraw(
                    account=account,
                    amount=amount,
                    created_by=request.user,
                    description=description,
                )
                account.refresh_from_db()
                return Response({
                    "message": "Withdrawal successful.",
                    "transaction_id": txn.transaction_id,
                    "account_number": account.account_number,
                    "available_balance": str(account.available_balance),
                    "ledger_balance": str(account.ledger_balance),
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TransferAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = TransferSerializer(data=request.data)
        if serializer.is_valid():
            from_account = Account.objects.get(account_number=serializer.validated_data['from_account_number'])
            to_account = Account.objects.get(account_number=serializer.validated_data['to_account_number'])
            amount = serializer.validated_data['amount']
            description = serializer.validated_data.get('description', '')

            try:
                txn = transfer(
                    from_account=from_account,
                    to_account=to_account,
                    amount=amount,
                    created_by=request.user,
                    description=description,
                )
                from_account.refresh_from_db()
                to_account.refresh_from_db()
                return Response({
                    "message": "Transfer successful.",
                    "transaction_id": txn.transaction_id,
                    "from_account_number": from_account.account_number,
                    "from_available_balance": str(from_account.available_balance),
                    "to_account_number": to_account.account_number,
                    "to_available_balance": str(to_account.available_balance),
                }, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
