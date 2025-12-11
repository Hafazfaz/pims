from django.db import models
from django.conf import settings

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    head = models.OneToOneField(
        'Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_department'
    )

    def __str__(self):
        return self.name

class Unit(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='units')
    head = models.OneToOneField(
        'Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='headed_unit'
    )

    def __str__(self):
        return f"{self.name} ({self.department.code})"

class Designation(models.Model):
    name = models.CharField(max_length=100, unique=True)
    level = models.PositiveIntegerField()

    class Meta:
        ordering = ['level']

    def __str__(self):
        return self.name

class Staff(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='staff_members')
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_members')
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        try:
            return self.user.get_full_name() or self.user.username
        except AttributeError:
            return self.user.username
