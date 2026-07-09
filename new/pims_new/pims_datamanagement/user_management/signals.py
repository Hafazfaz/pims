from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.dispatch import receiver

MAX_CONCURRENT_SESSIONS = getattr(settings, "MAX_CONCURRENT_SESSIONS", 3)


@receiver(user_logged_in)
def enforce_session_limit(sender, request, user, **kwargs):
    from .models import UserSession

    # Record the new session
    if not request.session.session_key:
        request.session.save()
    UserSession.objects.get_or_create(user=user, session_key=request.session.session_key)

    # Evict oldest sessions beyond the limit
    sessions = UserSession.objects.filter(user=user).order_by("created_at")
    overflow = sessions.count() - MAX_CONCURRENT_SESSIONS
    if overflow > 0:
        oldest_pks = list(sessions.values_list("pk", flat=True)[:overflow])
        old_keys = list(UserSession.objects.filter(pk__in=oldest_pks).values_list("session_key", flat=True))
        Session.objects.filter(session_key__in=old_keys).delete()
        UserSession.objects.filter(pk__in=oldest_pks).delete()

    # Legacy: keep last_session_key in sync
    if getattr(settings, "SESSION_FLUSH_AT_LOGIN", False):
        for session in Session.objects.all():
            data = session.get_decoded()
            if str(data.get("_auth_user_id")) == str(user.pk) and session.session_key != request.session.session_key:
                session.delete()


@receiver(user_logged_out)
def cleanup_session_on_logout(sender, request, user, **kwargs):
    if user and request.session.session_key:
        from .models import UserSession

        UserSession.objects.filter(user=user, session_key=request.session.session_key).delete()
