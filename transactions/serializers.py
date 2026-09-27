from decimal import Decimal
from rest_framework import serializers
from accounts.models import Account


class DepositSerializer(serializers.Serializer):
    account_number = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Deposit amount must be positive.")
        return value

    def validate_account_number(self, value):
        try:
            account = Account.objects.get(account_number=value)
        except Account.DoesNotExist:
            raise serializers.ValidationError("Account not found.")
        if account.account_status != Account.AccountStatus.ACTIVE:
            raise serializers.ValidationError("Account is not active.")
        return value


class WithdrawSerializer(serializers.Serializer):
    account_number = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Withdrawal amount must be positive.")
        return value

    def validate_account_number(self, value):
        try:
            account = Account.objects.get(account_number=value)
        except Account.DoesNotExist:
            raise serializers.ValidationError("Account not found.")
        if account.account_status != Account.AccountStatus.ACTIVE:
            raise serializers.ValidationError("Account is not active.")
        return value


class TransferSerializer(serializers.Serializer):
    from_account_number = serializers.CharField(max_length=20)
    to_account_number = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= Decimal('0.00'):
            raise serializers.ValidationError("Transfer amount must be positive.")
        return value

    def validate(self, data):
        from_acc_num = data.get('from_account_number')
        to_acc_num = data.get('to_account_number')

        if from_acc_num == to_acc_num:
            raise serializers.ValidationError("Source and destination accounts cannot be the same.")

        try:
            from_account = Account.objects.get(account_number=from_acc_num)
        except Account.DoesNotExist:
            raise serializers.ValidationError({"from_account_number": "Sender account not found."})

        if from_account.account_status != Account.AccountStatus.ACTIVE:
            raise serializers.ValidationError({"from_account_number": "Sender account is not active."})

        try:
            to_account = Account.objects.get(account_number=to_acc_num)
        except Account.DoesNotExist:
            raise serializers.ValidationError({"to_account_number": "Receiver account not found."})

        if to_account.account_status != Account.AccountStatus.ACTIVE:
            raise serializers.ValidationError({"to_account_number": "Receiver account is not active."})

        return data
