from core.constants import STAFF_TYPE_CHOICES
from django.conf import settings
from django.db import models
from django.db.models import Q

# Designation names that make a staff member a department head even when
# they were never wired up as ``Department.head``.
HOD_DESIGNATION_ROLES = ("head of department", "hod", "director")


def designation_implies_hod(designation):
    """True when a designation marks the holder as a department head."""
    if designation is None or not designation.name:
        return False
    lowered = designation.name.lower()
    return any(role in lowered for role in HOD_DESIGNATION_ROLES)


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)
    head = models.OneToOneField(
        "Staff", on_delete=models.SET_NULL, null=True, blank=True, related_name="headed_department"
    )

    def __str__(self):
        return self.name


class Division(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="divisions")
    head = models.OneToOneField(
        "Staff", on_delete=models.SET_NULL, null=True, blank=True, related_name="headed_division"
    )

    def __str__(self):
        return f"{self.name} ({self.department.code})"


class Section(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="sections")
    head = models.OneToOneField(
        "Staff", on_delete=models.SET_NULL, null=True, blank=True, related_name="headed_section"
    )

    def __str__(self):
        dept_code = self.department.code if self.department else "No Dept"
        return f"{self.name} ({dept_code})"


class Unit(models.Model):
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="units")
    division = models.ForeignKey(Division, on_delete=models.SET_NULL, null=True, blank=True, related_name="units")
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name="units")
    head = models.OneToOneField("Staff", on_delete=models.SET_NULL, null=True, blank=True, related_name="headed_unit")

    def __str__(self):
        return f"{self.name} ({self.department.code})"


class Designation(models.Model):
    name = models.CharField(max_length=100, unique=True)
    level = models.PositiveIntegerField()

    class Meta:
        ordering = ["level"]

    def __str__(self):
        return self.name


class Staff(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    designation = models.ForeignKey(Designation, on_delete=models.SET_NULL, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, related_name="staff_members")
    division = models.ForeignKey(
        Division, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_members"
    )
    section = models.ForeignKey(Section, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_members")
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_members")
    staff_type = models.CharField(max_length=20, choices=STAFF_TYPE_CHOICES, default="permanent")

    phone_number = models.CharField(max_length=20, blank=True, null=True)
    signature = models.ImageField(upload_to="signatures/", blank=True, null=True)
    is_supervisor = models.BooleanField(default=False, help_text="Designates this staff member as a supervisor.")

    def __str__(self):
        try:
            return self.user.get_full_name() or self.user.username
        except AttributeError:
            return self.user.username

    def get_active_signature(self):
        return self.signatures.filter(is_active=True).first()

    @property
    def is_registry(self):
        return self.user.has_perm("user_management.can_manage_registry")

    @property
    def is_hod(self):
        """Department-head scope — backed by ``user_management.can_head_department``.

        The permission is granted by the organization signals whenever this
        staff is appointed ``Department.head`` or given an HOD-level
        designation. Superusers hold every permission implicitly, so they
        fall back to the structural check — otherwise every admin would count
        as a department head.
        """
        if self.user.is_superuser:
            if designation_implies_hod(self.designation):
                return True
            try:
                return self.headed_department is not None
            except Exception:
                return False
        return self.user.has_perm("user_management.can_head_department")

    @property
    def is_head_of_unit(self):
        """Head-of-unit scope — backed by ``user_management.can_head_unit``.

        Granted by the organization signals when this staff is appointed
        ``Unit.head``. Superusers fall back to the structural check, as in
        :meth:`is_hod`.
        """
        if self.user.is_superuser:
            try:
                return self.headed_unit is not None
            except Exception:
                return False
        return self.user.has_perm("user_management.can_head_unit")

    @property
    def is_head_of_division(self):
        try:
            return self.headed_division is not None
        except Exception:
            return False

    @property
    def is_head_of_section(self):
        try:
            return self.headed_section is not None
        except Exception:
            return False

    # Keep backwards-compat alias
    @property
    def is_unit_manager(self):
        return self.is_head_of_unit

    @property
    def is_effective_supervisor(self):
        """True if this staff acts as a supervisor (permission-based or flagged)."""
        return (
            self.is_supervisor
            or self.is_head_of_unit
            or self.is_head_of_section
            or self.is_head_of_division
            or self.is_hod
            or self.user.has_perm("user_management.can_supervise")
            or self.user.has_perm("user_management.can_executive")
        )

    @property
    def is_privileged_head(self):
        """Oversight heads: HOD / section / division heads, flagged supervisors,
        executives, MD, Mayor — but NOT pure heads-of-unit, who are treated
        like regular staff for viewing personnel documents.

        Pure heads-of-unit are excluded even though they hold
        ``can_supervise`` through the Supervisor group: they are recognised
        separately via :attr:`is_head_of_unit`.
        """
        if self.is_hod or self.is_head_of_section or self.is_head_of_division:
            return True
        if self.is_supervisor:
            return True
        if not self.is_head_of_unit and self.user.has_perm("user_management.can_supervise"):
            return True
        return self.user.has_perm("user_management.can_executive")

    @property
    def is_executive(self):
        return self.user.has_perm("user_management.can_executive")

    @property
    def is_md(self):
        return self.user.has_perm("user_management.can_executive")

    @property
    def is_mayor(self):
        """Custom Mayor role — via the executive permission bundle."""
        return self.user.has_perm("user_management.can_executive")

    @property
    def role_label(self):
        """Role-first meta shown wherever a recipient is picked.

        Executives show their designation ("Medical Director", "Executive
        Director"); department heads show ``HOD (<department>)``; unit heads
        show ``HOU (<unit>)``; everyone else falls back to
        ``Designation · Department``.
        """
        designation = getattr(getattr(self, "designation", None), "name", "") or ""
        department = getattr(getattr(self, "department", None), "name", "") or ""
        unit = getattr(getattr(self, "unit", None), "name", "") or ""
        if self.is_md or self.is_mayor or self.is_executive:
            return designation or "Executive"
        if self.is_hod:
            return f"HOD ({department})" if department else "HOD"
        if self.is_head_of_unit:
            return f"HOU ({unit})" if unit else "HOU"
        return " · ".join(part for part in [designation, department] if part)

    @property
    def dispatch_label(self):
        """``Full name — <role_label>`` for dispatch/forward selects and rows."""
        name = self.user.get_full_name() or self.user.username
        role = self.role_label
        return f"{name} — {role}" if role else name


class StaffSignature(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="signatures")
    image = models.ImageField(upload_to="signatures/verified/")
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Signature for {self.staff} ({'Active' if self.is_active else 'Inactive'})"

    def save(self, *args, **kwargs):
        if self.is_active:
            # Deactivate all other signatures for this staff if this one is active
            StaffSignature.objects.filter(staff=self.staff).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
