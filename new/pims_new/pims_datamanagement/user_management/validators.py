import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

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