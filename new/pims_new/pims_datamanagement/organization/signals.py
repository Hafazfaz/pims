from django.contrib.auth.models import Group
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import designation_implies_final_approver, designation_implies_hod


def _get_hod_group():
    group, _ = Group.objects.get_or_create(name="HOD/HOU")
    return group


def _get_supervisor_group():
    group, _ = Group.objects.get_or_create(name="Supervisor")
    return group


def _get_head_perm(codename):
    """Fetch (or create) one of the head-of-scope permissions on CustomUser."""
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    user_ct = ContentType.objects.get(app_label="user_management", model="customuser")
    perm, _ = Permission.objects.get_or_create(
        codename=codename,
        content_type=user_ct,
        defaults={"name": codename.replace("_", " ").title()},
    )
    return perm


def _set_user_perm(user, codename, enabled):
    perm = _get_head_perm(codename)
    if enabled:
        user.user_permissions.add(perm)
    else:
        user.user_permissions.remove(perm)
    # Drop any cached permission set so the next has_perm() re-reads the DB.
    for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        if attr in user.__dict__:
            del user.__dict__[attr]


def _sync_head_permissions(staff):
    """Keep ``can_head_department`` / ``can_head_unit`` in sync with reality.

    The permission — not the designation or the head FK — is what every gate
    now reads, so it must follow appointments exactly.
    """
    if not staff.user_id:
        return
    from .models import Department, Unit

    user = staff.user
    _set_user_perm(
        user,
        "can_head_department",
        designation_implies_hod(staff.designation) or Department.objects.filter(head=staff).exists(),
    )
    _set_user_perm(user, "can_head_unit", Unit.objects.filter(head=staff).exists())


def _sync_approve_permission(staff):
    """Keep ``can_approve_document`` tied to the Medical Director role only.

    Nothing else — no head appointment, no Supervisor/HOD group — carries
    final approval; everyone else routes their approval to an approver.
    """
    if not staff.user_id:
        return
    _set_user_perm(staff.user, "can_approve_document", designation_implies_final_approver(staff.designation))


def _is_still_head(staff):
    """Return True if staff is still head of any dept or unit."""
    from .models import Department, Unit

    return Department.objects.filter(head=staff).exists() or Unit.objects.filter(head=staff).exists()


def _sync_supervisor_group(staff):
    """Ensure a staff member is in the Supervisor group exactly when they are
    a department/unit head OR flagged as a supervisor."""
    if not staff.user_id:
        return
    group = _get_supervisor_group()
    is_supervisor = bool(staff.is_supervisor) or _is_still_head(staff)
    if is_supervisor:
        staff.user.groups.add(group)
    else:
        staff.user.groups.remove(group)


def _handle_head_change(old_head, new_head):
    group = _get_hod_group()
    if new_head:
        new_head.user.groups.add(group)
        _sync_supervisor_group(new_head)
        _sync_head_permissions(new_head)
    if old_head and old_head != new_head and not _is_still_head(old_head):
        old_head.user.groups.remove(group)
        _sync_supervisor_group(old_head)
        _sync_head_permissions(old_head)


@receiver(post_save, sender="organization.Staff")
def staff_supervisor_flag_post_save(sender, instance, **kwargs):
    """Keep the Supervisor group and head-of-scope permissions in sync with
    the ``is_supervisor`` flag, the designation, and head appointments."""
    _sync_supervisor_group(instance)
    _sync_head_permissions(instance)
    _sync_approve_permission(instance)


@receiver(pre_save, sender="organization.Department")
def department_head_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_head = None
        return
    try:
        instance._old_head = sender.objects.get(pk=instance.pk).head
    except sender.DoesNotExist:
        instance._old_head = None


@receiver(post_save, sender="organization.Department")
def department_head_post_save(sender, instance, **kwargs):
    old_head = getattr(instance, "_old_head", None)
    _handle_head_change(old_head, instance.head)


@receiver(pre_save, sender="organization.Unit")
def unit_head_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_head = None
        return
    try:
        instance._old_head = sender.objects.get(pk=instance.pk).head
    except sender.DoesNotExist:
        instance._old_head = None


@receiver(post_save, sender="organization.Unit")
def unit_head_post_save(sender, instance, **kwargs):
    old_head = getattr(instance, "_old_head", None)
    _handle_head_change(old_head, instance.head)
