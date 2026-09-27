from django.db import models


class Branch(models.Model):
    branch_code = models.CharField(max_length=20, unique=True)
    branch_name = models.CharField(max_length=150)
    routing_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    address = models.TextField()
    district = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        ordering = ['branch_code']

    def __str__(self):
        return f"{self.branch_code} - {self.branch_name}"
