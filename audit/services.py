"""Write activity-log entries. Call record() from a view, next to the change it describes."""
from accounts.access import get_staff

from .models import AuditEntry


def record(request, action, summary):
    """Log that the signed-in user did something in their organisation (request.staff, or looked up from the user)."""
    staff = getattr(request, "staff", None) or get_staff(request.user)
    if staff is None:
        return None
    return AuditEntry.objects.create(
        organization=staff.organization,
        actor=request.user,
        actor_name=(request.user.get_full_name() or request.user.get_username())[:150],
        action=action[:60],
        summary=str(summary)[:300],
    )
