from audit.models import AuditLog


class AuditService:
    @staticmethod
    def log(action, user_identifier, details=""):
        return AuditLog.objects.create(
            action=action,
            user_identifier=user_identifier,
            details=details,
        )

    @staticmethod
    def get_recent(limit=20):
        return AuditLog.objects.order_by("-timestamp")[:limit]

    @staticmethod
    def filter_by_action(action_type):
        return AuditLog.objects.filter(action=action_type)

    @staticmethod
    def filter_by_user(user_identifier):
        return AuditLog.objects.filter(user_identifier__icontains=user_identifier)

    @staticmethod
    def get_action_types():
        return (
            AuditLog.objects.values_list("action", flat=True)
            .distinct()
            .order_by("action")
        )
