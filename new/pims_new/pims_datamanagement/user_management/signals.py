from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.sessions.models import Session
from django.dispatch import receiver


def _max_sessions():
    try:
        return int(getattr(settings, "MAX_CONCURRENT_SESSIONS", 2))
    except (TypeError, ValueError):
        return 2


@receiver(user_logged_in)
def enforce_session_limit(sender, request, user, **kwargs):
    from .models import UserSession

    # Record the new session
    if not request.session.session_key:
        request.session.save()
    UserSession.objects.get_or_create(user=user, session_key=request.session.session_key)

    # Prune stale tracking rows whose Django session no longer exists
    # (expired / browser-closed sessions) so they don't count toward the limit.
    live_keys = set(Session.objects.values_list("session_key", flat=True))
    UserSession.objects.filter(user=user).exclude(session_key__in=live_keys).delete()

    # Evict oldest sessions beyond the limit
    sessions = UserSession.objects.filter(user=user).order_by("created_at")
    overflow = sessions.count() - _max_sessions()
    if overflow > 0:
        oldest_pks = list(sessions.values_list("pk", flat=True)[:overflow])
        old_keys = list(UserSession.objects.filter(pk__in=oldest_pks).values_list("session_key", flat=True))
        Session.objects.filter(session_key__in=old_keys).delete()
        UserSession.objects.filter(pk__in=oldest_pks).delete()

    # Keep legacy last_session_key in sync
    try:
        user.last_session_key = request.session.session_key
        user.save(update_fields=["last_session_key"])
    except Exception:
        pass


@receiver(user_logged_out)
def cleanup_session_on_logout(sender, request, user, **kwargs):
    if user and request.session.session_key:
        from .models import UserSession

        UserSession.objects.filter(user=user, session_key=request.session.session_key).delete()
