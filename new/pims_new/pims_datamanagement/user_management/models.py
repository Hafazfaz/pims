from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    must_change_password = models.BooleanField(default=False)