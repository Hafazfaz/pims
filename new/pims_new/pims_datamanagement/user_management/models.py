from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    must_change_password = models.BooleanField(default=False)
    failed_login_attempts = models.IntegerField(default=0)
    lockout_until = models.DateTimeField(null=True, blank=True)