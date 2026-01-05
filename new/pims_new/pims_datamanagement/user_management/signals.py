from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.dispatch import receiver
from django.conf import settings

@receiver(user_logged_in)
def invalidate_previous_sessions(sender, request, user, **kwargs):
    # Only invalidate if concurrent sessions are explicitly disallowed
    if getattr(settings, 'SESSION_FLUSH_AT_LOGIN', False):
        # Delete all sessions for the current user except the current one
        for session in Session.objects.all():
            session_data = session.get_decoded()
            if str(session_data.get('_auth_user_id')) == str(user.pk) and \
               session.session_key != request.session.session_key:
                session.delete()

