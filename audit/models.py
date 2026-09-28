from django.db import models
from django.contrib.auth.models import User


class AuditLog(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name="User",
    )
    action = models.CharField(max_length=100, verbose_name="Action")
    model_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Model Name")
    object_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Object ID")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP Address")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.ip_address == '':
            self.ip_address = None
        super().save(*args, **kwargs)

    def __str__(self):
        user_str = self.user.username if self.user else "System"
        target_str = f" - {self.model_name}" if self.model_name else ""
        if self.object_id:
            target_str += f" ({self.object_id})"
        return f"{self.action}{target_str} by {user_str}"
