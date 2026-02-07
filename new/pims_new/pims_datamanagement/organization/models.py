from django.db import models
from django.conf import settings
from core.constants import STAFF_TYPE_CHOICES


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
    staff_type = models.CharField(max_length=20, choices=STAFF_TYPE_CHOICES, default='permanent')

    phone_number = models.CharField(max_length=20, blank=True, null=True)
    signature = models.ImageField(upload_to='signatures/', blank=True, null=True) # Legacy signature field

    def __str__(self):
        try:
            return self.user.get_full_name() or self.user.username
        except AttributeError:
            return self.user.username

    def get_active_signature(self):
        return self.signatures.filter(is_active=True).first()
    @property
    def is_registry(self):
        if self.designation and "registry" in self.designation.name.lower():
            return True
        return self.user.groups.filter(name__iexact="Registry").exists()

    @property
    def is_hod(self):
        if self.designation and any(role in self.designation.name.lower() for role in ["head of department", "hod", "director"]):
            return True
        return hasattr(self, 'headed_department') and self.headed_department is not None

    @property
    def is_unit_manager(self):
        return hasattr(self, 'headed_unit') and self.headed_unit is not None

    @property
    def is_executive(self):
        return self.user.groups.filter(name__iexact="Executives").exists()
class StaffSignature(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='signatures')
    image = models.ImageField(upload_to='signatures/verified/')
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Signature for {self.staff} ({'Verified' if self.is_verified else 'Pending'})"

    def save(self, *args, **kwargs):
        if self.is_active:
            # Deactivate all other signatures for this staff if this one is active
            StaffSignature.objects.filter(staff=self.staff).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

