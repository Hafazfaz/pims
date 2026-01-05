import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.contrib.auth.hashers import check_password # Import check_password
from .models import PasswordHistory # Import PasswordHistory
from .views import PASSWORD_HISTORY_LIMIT # Import the limit constant

class CustomPasswordValidator:
    def __init__(self, min_length=10):
        self.min_length = min_length

    def validate(self, password, user=None):
        if len(password) < self.min_length:
            raise ValidationError(
                _("This password must contain at least %(min_length)d characters."),
                code='password_too_short',
                params={'min_length': self.min_length},
            )
        if not re.search(r'[A-Z]', password):
            raise ValidationError(
                _("This password must contain at least 1 uppercase letter."),
                code='password_no_uppercase',
            )
        if not re.search(r'[a-z]', password):
            raise ValidationError(
                _("This password must contain at least 1 lowercase letter."),
                code='password_no_lowercase',
            )
        if not re.search(r'\d', password):
            raise ValidationError(
                _("This password must contain at least 1 digit."),
                code='password_no_digit',
            )
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:",.<>/?`~]', password):
            raise ValidationError(
                _("This password must contain at least 1 special character."),
                code='password_no_special',
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least %(min_length)d characters, "
            "including at least 1 uppercase letter, 1 lowercase letter, 1 digit, and 1 special character."
        ) % {'min_length': self.min_length}


class PasswordHistoryValidator:
    def validate(self, password, user=None):
        if not user:
            return

        # Get the last N password hashes from history
        history_entries = PasswordHistory.objects.filter(user=user).order_by('-timestamp')[:PASSWORD_HISTORY_LIMIT]

        for entry in history_entries:
            if check_password(password, entry.password):
                raise ValidationError(
                    _("You cannot reuse a password from your last %(limit)d passwords."),
                    code='password_reuse',
                    params={'limit': PASSWORD_HISTORY_LIMIT},
                )

    def get_help_text(self):
        return _(
            "Your new password cannot be one of your last %(limit)d passwords."
        ) % {'limit': PASSWORD_HISTORY_LIMIT}