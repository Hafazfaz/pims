from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group


def _get_hod_group():
    group, _ = Group.objects.get_or_create(name='HOD/HOU')
    return group


def _is_still_head(staff):
    """Return True if staff is still head of any dept or unit."""
    from .models import Department, Unit
    return (
        Department.objects.filter(head=staff).exists() or
        Unit.objects.filter(head=staff).exists()
    )


def _handle_head_change(old_head, new_head):
    group = _get_hod_group()
    if new_head:
        new_head.user.groups.add(group)
    if old_head and old_head != new_head and not _is_still_head(old_head):
        old_head.user.groups.remove(group)


@receiver(pre_save, sender='organization.Department')
def department_head_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_head = None
        return
    try:
        instance._old_head = sender.objects.get(pk=instance.pk).head
    except sender.DoesNotExist:
        instance._old_head = None


@receiver(post_save, sender='organization.Department')
def department_head_post_save(sender, instance, **kwargs):
    old_head = getattr(instance, '_old_head', None)
    _handle_head_change(old_head, instance.head)


@receiver(pre_save, sender='organization.Unit')
def unit_head_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_head = None
        return
    try:
        instance._old_head = sender.objects.get(pk=instance.pk).head
    except sender.DoesNotExist:
        instance._old_head = None


@receiver(post_save, sender='organization.Unit')
def unit_head_post_save(sender, instance, **kwargs):
    old_head = getattr(instance, '_old_head', None)
    _handle_head_change(old_head, instance.head)
