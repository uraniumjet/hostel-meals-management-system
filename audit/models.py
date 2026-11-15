from django.conf import settings
from django.db import models

from organizations.models import Organization


class AuditEntry(models.Model):
    """One line in the activity log: who did what, and when. Entries are written by code and never edited."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="audit_entries")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_name = models.CharField(max_length=150, blank=True)  # kept even if the account is deleted later
    action = models.CharField(max_length=60)  # "area.what", for example "student.moved"
    summary = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["organization", "-created_at"], name="audit_org_created_idx")]
        verbose_name_plural = "audit entries"

    def __str__(self):
        return f"{self.actor_name}: {self.summary}"

    @property
    def area(self):
        return self.action.split(".", 1)[0]
