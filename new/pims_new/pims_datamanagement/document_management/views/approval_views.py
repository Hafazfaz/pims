from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, View, DetailView, ListView
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.utils import timezone
from django.urls import reverse_lazy
from django.http import JsonResponse
import json
from ..models import File, ApprovalChain, ApprovalStep, ChainTemplate, ChainTemplateStep
from .base import HTMXLoginRequiredMixin, RegistryRequiredMixin
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
    template_name = "document_management/my_chains.html"
    context_object_name = "chains"

    def get_queryset(self):
        staff = getattr(self.request.user, 'staff', None)
        if not staff:
            return ApprovalChain.objects.none()
        from django.db.models import Q
        return ApprovalChain.objects.filter(
            Q(file__owner=staff) | Q(created_by=self.request.user) | Q(steps__approver=staff)
        ).distinct().select_related('file', 'document').prefetch_related('steps')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['staff'] = getattr(self.request.user, 'staff', None)
        return context


class ApprovalChainBuilderView(HTMXLoginRequiredMixin, View):
    """Visual canvas-based chain builder page."""

    def get(self, request, file_pk):
        from django.shortcuts import render
        from organization.models import Staff as StaffModel
        file_obj = get_object_or_404(File, pk=file_pk)
        staff = getattr(request.user, 'staff', None)

        if file_obj.owner != staff and file_obj.created_by != request.user:
            messages.error(request, "Only the file owner can build an approval chain.")
            return redirect(file_obj.get_absolute_url())

        if file_obj.is_in_active_chain:
            messages.error(request, "This file already has an approval chain.")
            return redirect(file_obj.get_absolute_url())

        from document_management.views.base import EXCLUDE_REGISTRY_Q
        approver_choices = StaffModel.objects.exclude(EXCLUDE_REGISTRY_Q).exclude(
            user=request.user
        ).select_related('user', 'designation', 'department').order_by('user__last_name')

        return render(request, 'document_management/chain_builder.html', {
            'file': file_obj,
            'approver_choices': approver_choices,
        })




class ApprovalChainCreateView(HTMXLoginRequiredMixin, View):
    """Owner sets up the approval chain for their file."""

    def post(self, request, file_pk):
        file_obj = get_object_or_404(File, pk=file_pk)
        staff = getattr(request.user, 'staff', None)

        if file_obj.owner != staff and file_obj.created_by != request.user:
            messages.error(request, "Only the file owner can set up an approval chain.")
            return redirect(file_obj.get_absolute_url())

        if file_obj.status not in ('active', 'inactive'):
            messages.error(request, "File must be active or inactive to start an approval chain.")
            return redirect(file_obj.get_absolute_url())

        if file_obj.is_in_active_chain:
            messages.error(request, "This file already has an approval chain.")
            return redirect(file_obj.get_absolute_url())

        approver_ids = [a for a in request.POST.getlist('approvers') if a]
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
    """Owner starts the chain — dispatches file to step 1 in read-only mode."""

    def post(self, request, file_pk):
        file_obj = get_object_or_404(File, pk=file_pk)
        # Find draft chain on any document in this file
        chain = ApprovalChain.objects.filter(file=file_obj, status='draft').first()
        if not chain:
            messages.error(request, "No draft chain found for this file.")
            return redirect(file_obj.get_absolute_url())

        staff = getattr(request.user, 'staff', None)
        if file_obj.owner != staff and file_obj.created_by != request.user:
            messages.error(request, "Only the file owner can start the approval chain.")
            return redirect(file_obj.get_absolute_url())

        if not chain.steps.exists():
            messages.error(request, "Add at least one approver before starting.")
            return redirect(file_obj.get_absolute_url())

        first_step = chain.steps.order_by('order').first()
        chain.status = 'active'
        chain.current_step = first_step.order
        chain.save()

        # File goes to first approver in read-only mode (status unchanged)
        file_obj.current_location = first_step.approver
        file_obj.save()

        _notify_approver(first_step)
        messages.success(request, f"Chain started. File dispatched to {first_step.approver} in read-only mode.")
        return redirect(file_obj.get_absolute_url())


class ApprovalStepActionView(HTMXLoginRequiredMixin, View):
    """Current approver approves or rejects their step."""

    def post(self, request, step_pk):
        step = get_object_or_404(ApprovalStep, pk=step_pk)
        chain = step.chain
        file_obj = chain._get_file()
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
            if chain.status == 'active':
                next_step = chain.get_current_step()
                if next_step:
                    _notify_approver(next_step)
            elif chain.status == 'closed':
                _notify_owner(chain, f"Approval chain for '{chain.document or chain._get_file().file_number}' has been completed. File returned to registry.")
            messages.success(request, "Step approved.")
        elif action == 'reject':
            step.status = 'rejected'
            step.save()
            chain.reject_to_previous(step.order)
            _notify_owner(chain, f"Step {step.order} was rejected. Note: {step.note or 'No reason given'}")
            messages.warning(request, "Step rejected. File sent back.")
        else:
            messages.error(request, "Invalid action.")

        return redirect(file_obj.get_absolute_url())


class ApprovalChainDeleteView(HTMXLoginRequiredMixin, View):
    """Owner can delete a draft chain."""

    def post(self, request, file_pk):
        file_obj = get_object_or_404(File, pk=file_pk)
        chain = ApprovalChain.objects.filter(file=file_obj, status='draft').first()
        if not chain:
            messages.error(request, "No draft chain found.")
            return redirect(file_obj.get_absolute_url())

        staff = getattr(request.user, 'staff', None)
        if file_obj.owner != staff and file_obj.created_by != request.user:
            messages.error(request, "Only the file owner can delete the chain.")
            return redirect(file_obj.get_absolute_url())

        chain.delete()
        messages.success(request, "Approval chain deleted.")
        return redirect(file_obj.get_absolute_url())


class ChainTemplateListView(RegistryRequiredMixin, ListView):
    model = ChainTemplate
    template_name = 'document_management/chain_template_list.html'
    context_object_name = 'templates'

    def get_queryset(self):
        return ChainTemplate.objects.select_related('department', 'created_by').prefetch_related('steps').order_by('-created_at')


class ChainTemplateBuilderView(RegistryRequiredMixin, View):
    """Canvas-based chain template builder for admin/registry."""

    def get(self, request, pk=None):
        from organization.models import Department, Designation, Staff as StaffModel
        template = get_object_or_404(ChainTemplate, pk=pk) if pk else None
        departments = Department.objects.all().order_by('name')
        designations = Designation.objects.all().order_by('level')
        staff_list = StaffModel.objects.select_related('user', 'designation', 'department').order_by('user__last_name')

        existing_steps = []
        if template:
            for step in template.steps.all():
                existing_steps.append({
                    'order': step.order,
                    'role_type': step.role_type,
                    'department_scope': step.department_scope,
                    'specific_department_id': step.specific_department_id,
                    'designation_id': step.designation_id,
                    'staff_id': step.staff_id,
                    'label': str(step),
                })

        return render(request, 'document_management/chain_template_builder.html', {
            'template': template,
            'departments': departments,
            'designations': designations,
            'staff_list': staff_list,
            'existing_steps_json': json.dumps(existing_steps),
        })

    def post(self, request, pk=None):
        from organization.models import Department, Designation, Staff as StaffModel
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        dept_id = request.POST.get('department') or None

        if not name:
            messages.error(request, "Template name is required.")
            return redirect(request.path)

        if pk:
            tmpl = get_object_or_404(ChainTemplate, pk=pk)
            tmpl.name = name
            tmpl.description = description
            tmpl.department_id = dept_id
            tmpl.save()
            tmpl.steps.all().delete()
        else:
            tmpl = ChainTemplate.objects.create(
                name=name, description=description,
                department_id=dept_id, created_by=request.user
            )

        steps_json = request.POST.get('steps_json', '[]')
        try:
            steps = json.loads(steps_json)
        except json.JSONDecodeError:
            steps = []

        for i, step in enumerate(steps, start=1):
            ChainTemplateStep.objects.create(
                template=tmpl,
                order=i,
                role_type=step.get('role_type', 'specific_person'),
                department_scope=step.get('department_scope', 'sender'),
                specific_department_id=step.get('specific_department_id') or None,
                designation_id=step.get('designation_id') or None,
                staff_id=step.get('staff_id') or None,
            )

        messages.success(request, f"Chain template '{tmpl.name}' saved.")
        return redirect(reverse_lazy('document_management:chain_template_list'))


class ChainTemplateDeleteView(RegistryRequiredMixin, View):
    def post(self, request, pk):
        tmpl = get_object_or_404(ChainTemplate, pk=pk)
        tmpl.delete()
        messages.success(request, "Template deleted.")
        return redirect(reverse_lazy('document_management:chain_template_list'))


class ApplyChainTemplateView(HTMXLoginRequiredMixin, View):
    """Staff applies a chain template to a specific document when dispatching."""

    def post(self, request, file_pk):
        from document_management.models import FileAccessRequest, Document
        from django.db.models import Q
        file_obj = get_object_or_404(File, pk=file_pk)
        staff = getattr(request.user, 'staff', None)

        if not staff:
            messages.error(request, "Staff profile not found.")
            return redirect(file_obj.get_absolute_url())

        # Must have read+write access or be custodian/owner
        has_rw = (
            file_obj.owner == staff or
            file_obj.current_location == staff or
            FileAccessRequest.objects.filter(
                file=file_obj, requested_by=request.user,
                status='approved', access_type='read_write'
            ).filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True)).exists()
        )
        if not has_rw:
            messages.error(request, "You need read & write access to dispatch a chain.")
            return redirect(file_obj.get_absolute_url())

        template_id = request.POST.get('template_id')
        document_id = request.POST.get('document_id')

        tmpl = get_object_or_404(ChainTemplate, pk=template_id, is_active=True)
        document = get_object_or_404(Document, pk=document_id, file=file_obj)

        if hasattr(document, 'approval_chain'):
            messages.error(request, "This document already has an approval chain.")
            return redirect(file_obj.get_absolute_url())

        chain = ApprovalChain.objects.create(
            document=document, file=file_obj,
            created_by=request.user, status='draft'
        )
        unresolved = []
        for step in tmpl.steps.all():
            approver = step.resolve(staff)
            if not approver:
                unresolved.append(str(step))
                continue
            ApprovalStep.objects.create(chain=chain, approver=approver, order=step.order)

        if unresolved:
            messages.warning(request, f"Chain applied but could not resolve: {', '.join(unresolved)}")
        else:
            messages.success(request, f"Chain '{tmpl.name}' applied to document. Start it to dispatch.")

        return redirect(file_obj.get_absolute_url())
