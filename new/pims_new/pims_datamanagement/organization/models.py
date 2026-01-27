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
    STAFF_TYPE_CHOICES = [
        ('permanent', 'Permanent'),
        ('locum', 'Locum'),
        ('contract', 'Contract'),
        ('nysc', 'NYSC'),
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name='staff_members')
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name='staff_members')
    staff_type = models.CharField(max_length=20, choices=STAFF_TYPE_CHOICES, default='permanent')
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        try:
            return self.user.get_full_name() or self.user.username
        except AttributeError:
            return self.user.username

    @property
    def is_registry(self):
        if self.designation and "registry" in self.designation.name.lower():
            return True
        return False

    @property
    def is_hod(self):
        if self.designation and any(role in self.designation.name.lower() for role in ["head of department", "hod", "director"]):
            return True
        return False
