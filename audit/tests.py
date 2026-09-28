from datetime import timedelta
from django.test import TestCase
from django.contrib.auth.models import User
from django.contrib import admin
from django.utils import timezone
from audit.models import AuditLog


class AuditLogModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="auditor1",
            email="auditor1@agranicbs.com",
            password="Password123!",
            first_name="Auditor",
            last_name="One",
        )

    def test_audit_log_creation(self):
        """Test creating an audit log with all fields populated."""
        log = AuditLog.objects.create(
            user=self.user,
            action="CREATE",
            model_name="Account",
            object_id="ACC00000001",
            description="Opened a new savings account for customer",
            ip_address="192.168.1.50",
        )

        self.assertIsNotNone(log.pk)
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, "CREATE")
        self.assertEqual(log.model_name, "Account")
        self.assertEqual(log.object_id, "ACC00000001")
        self.assertEqual(log.description, "Opened a new savings account for customer")
        self.assertEqual(log.ip_address, "192.168.1.50")
        self.assertIsNotNone(log.created_at)

    def test_audit_log_creation_optional_ip_address(self):
        """Test creating an audit log without ip_address (optional field)."""
        log = AuditLog.objects.create(
            user=self.user,
            action="UPDATE",
            model_name="Customer",
            object_id="CIF00000001",
            description="Updated KYC status",
        )

        self.assertIsNotNone(log.pk)
        self.assertIsNone(log.ip_address)

    def test_user_relationship(self):
        """Test ForeignKey relationship between AuditLog and User, including reverse relation."""
        log1 = AuditLog.objects.create(
            user=self.user,
            action="DEPOSIT_APPROVED",
            model_name="Transaction",
            object_id="TXN00000001",
            description="Approved cash deposit",
        )
        log2 = AuditLog.objects.create(
            user=self.user,
            action="TRANSFER_APPROVED",
            model_name="Transaction",
            object_id="TXN00000002",
            description="Approved fund transfer",
        )

        # Forward relationship
        self.assertEqual(log1.user, self.user)
        self.assertEqual(log2.user, self.user)

        # Reverse relationship
        user_logs = self.user.audit_logs.all()
        self.assertEqual(user_logs.count(), 2)
        self.assertIn(log1, user_logs)
        self.assertIn(log2, user_logs)

    def test_user_relationship_nullable_for_system_actions(self):
        """Test that user can be None for automated/system operations."""
        system_log = AuditLog.objects.create(
            user=None,
            action="SYSTEM_EOD",
            model_name="BatchJob",
            object_id="EOD-2026-09-28",
            description="End-of-day batch processing executed",
        )

        self.assertIsNotNone(system_log.pk)
        self.assertIsNone(system_log.user)

    def test_timestamp_creation(self):
        """Test created_at timestamp is automatically generated and accurate."""
        before = timezone.now() - timedelta(seconds=2)
        log = AuditLog.objects.create(
            user=self.user,
            action="LOGIN",
            description="User logged into CBS",
            ip_address="127.0.0.1",
        )
        after = timezone.now() + timedelta(seconds=2)

        self.assertIsNotNone(log.created_at)
        self.assertTrue(before <= log.created_at <= after)

    def test_string_representation(self):
        """Test __str__ representation under different field combinations."""
        # Full object log with user
        log_with_target = AuditLog.objects.create(
            user=self.user,
            action="CREATE",
            model_name="Account",
            object_id="ACC00000001",
            description="Created account",
        )
        expected_str = f"CREATE - Account (ACC00000001) by {self.user.username}"
        self.assertEqual(str(log_with_target), expected_str)

        # Action without model/object target
        log_no_target = AuditLog.objects.create(
            user=self.user,
            action="LOGIN",
            description="User login",
        )
        self.assertEqual(str(log_no_target), f"LOGIN by {self.user.username}")

        # Action with model but no object_id
        log_model_only = AuditLog.objects.create(
            user=self.user,
            action="EXPORT",
            model_name="AccountReport",
            description="Exported report",
        )
        self.assertEqual(str(log_model_only), f"EXPORT - AccountReport by {self.user.username}")

        # System action (user is None)
        log_system = AuditLog.objects.create(
            user=None,
            action="BACKUP",
            description="Nightly backup",
        )
        self.assertEqual(str(log_system), "BACKUP by System")

    def test_ordering_most_recent_first(self):
        """Test that default ordering is by -created_at."""
        log1 = AuditLog.objects.create(user=self.user, action="ACTION_1")
        log2 = AuditLog.objects.create(user=self.user, action="ACTION_2")

        logs = list(AuditLog.objects.filter(pk__in=[log1.pk, log2.pk]))
        self.assertEqual(logs[0].pk, log2.pk)
        self.assertEqual(logs[1].pk, log1.pk)

    def test_admin_registration(self):
        """Test AuditLog is registered in Django admin site."""
        self.assertIn(AuditLog, admin.site._registry)
