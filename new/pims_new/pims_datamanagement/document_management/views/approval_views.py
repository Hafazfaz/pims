from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, View, DetailView, ListView
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse_lazy
from ..models import File, ApprovalChain, ApprovalStep
from .base import HTMXLoginRequiredMixin
from notifications.utils import create_notification


def _notify_approver(step):
    """Notify the approver that it's their turn."""
    create_notification(
        user=step.approver.user,
        message=f"You have a pending approval for file '{step.chain.file.file_number} — {step.chain.file.title}' (Step {step.order}).",
        obj=step.chain.file,
        link=step.chain.file.get_absolute_url(),
    )


def _notify_owner(chain, message):
    """Notify the file owner/creator."""
    create_notification(
        user=chain.created_by,
        message=message,
        obj=chain.file,
        link=chain.file.get_absolute_url(),
    )


class MyApprovalChainsView(HTMXLoginRequiredMixin, ListView):
    """Shows all approval chains for files owned by the current user,
    plus chains where the user is an approver."""
    template_name = "document_management/my_chains.html"
    context_object_name = "chains"

    def get_queryset(self):
        staff = getattr(self.request.user, 'staff', None)
        if not staff:
            return ApprovalChain.objects.none()
        # Chains on files I own
        owned = ApprovalChain.objects.filter(file__owner=staff)
        # Chains where I'm an approver
        as_approver = ApprovalChain.objects.filter(steps__approver=staff)
        return (owned | as_approver).distinct().select_related('file').prefetch_related('steps')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = getattr(self.request.user, 'staff', None)
        context['staff'] = staff
        return context


class ApprovalChainCreateView(HTMXLoginRequiredMixin, View):
    """Owner sets up the approval chain for their file."""

    def post(self, request, file_pk):
        file_obj = get_object_or_404(File, pk=file_pk)

        # Only owner or creator can set up chain
        staff = getattr(request.user, 'staff', None)
        if file_obj.owner != staff and file_obj.created_by != request.user:
            messages.error(request, "Only the file owner can set up an approval chain.")
            return redirect(file_obj.get_absolute_url())

        if file_obj.status not in ('active', 'inactive'):
            messages.error(request, "File must be active or inactive to start an approval chain.")
            return redirect(file_obj.get_absolute_url())

        if hasattr(file_obj, 'approval_chain'):
            messages.error(request, "This file already has an approval chain.")
            return redirect(file_obj.get_absolute_url())

        approver_ids = request.POST.getlist('approvers')
        if not approver_ids:
            messages.error(request, "Please select at least one approver.")
            return redirect(file_obj.get_absolute_url())

        from organization.models import Staff
        chain = ApprovalChain.objects.create(file=file_obj, created_by=request.user, status='draft')
        for order, staff_id in enumerate(approver_ids, start=1):
            approver = get_object_or_404(Staff, pk=staff_id)
            ApprovalStep.objects.create(chain=chain, approver=approver, order=order)

        messages.success(request, "Approval chain created. You can now start it.")
        return redirect(file_obj.get_absolute_url())


class ApprovalChainStartView(HTMXLoginRequiredMixin, View):
    """Owner starts the chain — locks the file and dispatches to step 1."""

    def post(self, request, file_pk):
        file_obj = get_object_or_404(File, pk=file_pk)
        chain = get_object_or_404(ApprovalChain, file=file_obj)

        staff = getattr(request.user, 'staff', None)
        if file_obj.owner != staff and file_obj.created_by != request.user:
            messages.error(request, "Only the file owner can start the approval chain.")
            return redirect(file_obj.get_absolute_url())

        if chain.status != 'draft':
            messages.error(request, "Chain has already been started.")
            return redirect(file_obj.get_absolute_url())

        if not chain.steps.exists():
            messages.error(request, "Add at least one approver before starting.")
            return redirect(file_obj.get_absolute_url())

        first_step = chain.steps.order_by('order').first()
        chain.status = 'active'
        chain.current_step = first_step.order
        chain.save()

        file_obj.status = 'in_review'
        file_obj.current_location = first_step.approver
        file_obj.save()

        _notify_approver(first_step)
        messages.success(request, f"Approval chain started. File sent to {first_step.approver}.")
        return redirect(file_obj.get_absolute_url())


class ApprovalStepActionView(HTMXLoginRequiredMixin, View):
    """Current approver approves or rejects their step."""

    def post(self, request, step_pk):
        step = get_object_or_404(ApprovalStep, pk=step_pk)
        chain = step.chain
        file_obj = chain.file
        staff = getattr(request.user, 'staff', None)

        if step.approver != staff:
            messages.error(request, "You are not the assigned approver for this step.")
            return redirect(file_obj.get_absolute_url())

        if step.order != chain.current_step:
            messages.error(request, "This is not the current active step.")
            return redirect(file_obj.get_absolute_url())

        # Enforce signature
        active_sig = staff.get_active_signature() if staff else None
        if not active_sig:
            messages.error(request, "You must have an active signature to action this step. Please upload one in your profile.")
            return redirect(file_obj.get_absolute_url())

        action = request.POST.get('action')
        note = request.POST.get('note', '').strip()
        step.note = note
        step.signature = active_sig
        step.actioned_at = timezone.now()

        if action == 'approve':
            step.status = 'approved'
            step.save()
            chain.advance()
            # Notify next approver or owner if chain closed
            if chain.status == 'active':
                next_step = chain.get_current_step()
                if next_step:
                    _notify_approver(next_step)
            elif chain.status == 'closed':
                _notify_owner(chain, f"Approval chain for file '{chain.file.file_number}' has been completed.")
            messages.success(request, "Step approved.")
        elif action == 'reject':
            step.status = 'rejected'
            step.save()
            chain.reject_to_previous(step.order)
            _notify_owner(chain, f"Step {step.order} of the approval chain for file '{chain.file.file_number}' was rejected. Note: {step.note or 'No reason given'}")
            messages.warning(request, "Step rejected. File sent back.")
        else:
            messages.error(request, "Invalid action.")

        return redirect(file_obj.get_absolute_url())


class ApprovalChainDeleteView(HTMXLoginRequiredMixin, View):
    """Owner can delete a draft chain."""

    def post(self, request, file_pk):
        file_obj = get_object_or_404(File, pk=file_pk)
        chain = get_object_or_404(ApprovalChain, file=file_obj)

        staff = getattr(request.user, 'staff', None)
        if file_obj.owner != staff and file_obj.created_by != request.user:
            messages.error(request, "Only the file owner can delete the chain.")
            return redirect(file_obj.get_absolute_url())

        if chain.status != 'draft':
            messages.error(request, "Only draft chains can be deleted.")
            return redirect(file_obj.get_absolute_url())

        chain.delete()
        messages.success(request, "Approval chain deleted.")
        return redirect(file_obj.get_absolute_url())
