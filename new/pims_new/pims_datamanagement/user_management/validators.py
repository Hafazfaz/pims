import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from .models import PasswordHistory
from django.contrib.auth.hashers import check_password

class ComplexityValidator:
    """
    Validates that the password meets complexity requirements.
    """
    def __init__(self, min_length=12):
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
                _("This password must contain at least one uppercase letter."),
                code='password_no_upper',
            )
        if not re.search(r'[a-z]', password):
            raise ValidationError(
                _("This password must contain at least one lowercase letter."),
                code='password_no_lower',
            )
        if not re.search(r'[0-9]', password):
            raise ValidationError(
                _("This password must contain at least one number."),
                code='password_no_number',
            )
        if not re.search(r'[\W_]', password): # Checks for special characters
            raise ValidationError(
                _("This password must contain at least one special character."),
                code='password_no_symbol',
            )

    def get_help_text(self):
        return _(
            "Your password must contain at least %(min_length)d characters, including at least one uppercase letter, one lowercase letter, one number, and one special character."
        ) % {'min_length': self.min_length}


class PasswordHistoryValidator:
    """
    Validates that the password has not been used recently.
    """
    def __init__(self, history_limit=5):
        self.history_limit = history_limit

    def validate(self, password, user=None):
        if not user:
            return

        recent_passwords = PasswordHistory.objects.filter(user=user).order_by('-timestamp')[:self.history_limit]
        for entry in recent_passwords:
            if check_password(password, entry.password):
                raise ValidationError(
                    _("You cannot reuse one of your last %(history_limit)d passwords."),
                    code='password_reused',
                    params={'history_limit': self.history_limit},
                )

    def get_help_text(self):
        return _(
            "You cannot reuse one of your last %(history_limit)d passwords."
        ) % {'history_limit': self.history_limit}
