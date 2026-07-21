from datetime import timedelta

from audit_log.models import AuditLogEntry
from audit_log.utils import log_action
from django.contrib import messages
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UserPassesTestMixin,
)
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)
from notifications.utils import create_notification
from organization.models import Department, Staff

from ..forms import FileAccessRequestForm, FileForm, FileUpdateForm, SendFileForm
from ..models import Document, DocumentSignature, File, FileAccessRequest, FileMovement
from .base import EXCLUDE_REGISTRY_Q, HTMXLoginRequiredMixin


class ExecutiveDashboardView(HTMXLoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    Comprehensive dashboard for executives, HODs, and unit managers.
    Shows department/unit-specific metrics based on role.
    """

    template_name = "document_management/executive_dashboard.html"
    permission_required = "document_management.view_file"

    def test_func(self):
        staff_user = self.get_staff_user()
        return staff_user and (
            staff_user.is_hod or staff_user.is_unit_manager or staff_user.is_executive or staff_user.is_md
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_user = self.get_staff_user()

        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        if not (staff_user.is_hod or staff_user.is_unit_manager or staff_user.is_executive):
            raise PermissionDenied("Only executives, HODs, and unit managers can access this dashboard.")

        today = timezone.now().date()

        if self.request.user.is_superuser or staff_user.is_executive or staff_user.is_md:
            scope_filter = Q()
            context["scope_title"] = "Organization-Wide"
        elif staff_user.is_hod:
            scope_filter = Q(department=staff_user.department)
            context["scope_title"] = f"{staff_user.department.name} Department"
        elif staff_user.is_unit_manager:
            scope_filter = Q(owner__unit=staff_user.unit)
            context["scope_title"] = f"{staff_user.unit.name} Unit"
        else:
            scope_filter = Q(owner=staff_user)
            context["scope_title"] = "Personal"

        context["total_files"] = File.objects.filter(scope_filter).count()
        context["active_files"] = File.objects.filter(scope_filter, status="active").count()
        context["pending_activation"] = File.objects.filter(scope_filter, status="pending_activation").count()
        context["closed_files"] = File.objects.filter(scope_filter, status="closed").count()
        context["archived_files"] = File.objects.filter(scope_filter, status="archived").count()

        context["personal_files_count"] = File.objects.filter(scope_filter, file_type="personal").count()
        context["policy_files_count"] = File.objects.filter(scope_filter, file_type="policy").count()

        registry_staff_ids = Staff.objects.filter(
            Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
        ).values_list("id", flat=True)

        outgoing_files = (
            File.objects.filter(scope_filter, status="active")
            .exclude(Q(current_location__isnull=True) | Q(current_location__id__in=registry_staff_ids))
            .select_related("current_location", "owner", "department")
        )

        overdue_list = []
        for f in outgoing_files:
            if f.is_overdue():
                overdue_list.append({"file": f, "custody_duration": f.get_custody_duration()})

        context["overdue_files"] = overdue_list[:10]
        context["overdue_count"] = len(overdue_list)
        context["outgoing_files_count"] = outgoing_files.count()

        context["recent_files"] = File.objects.filter(scope_filter).order_by("-created_at")[:10]

        context["docs_added_today"] = Document.objects.filter(
            file__in=File.objects.filter(scope_filter), uploaded_at__date=today
        ).count()

        context["files_created_this_week"] = File.objects.filter(
            scope_filter, created_at__gte=today - timedelta(days=7)
        ).count()

        if staff_user.is_hod:
            context["total_staff"] = Staff.objects.filter(department=staff_user.department).count()
            staff_with_files = (
                File.objects.filter(scope_filter, file_type="personal").values_list("owner_id", flat=True).distinct()
            )
            context["staff_with_files_count"] = len(staff_with_files)
            context["staff_without_files_count"] = context["total_staff"] - context["staff_with_files_count"]

        elif staff_user.is_unit_manager:
            context["total_staff"] = Staff.objects.filter(unit=staff_user.unit).count()
            staff_with_files = (
                File.objects.filter(scope_filter, file_type="personal").values_list("owner_id", flat=True).distinct()
            )
            context["staff_with_files_count"] = len(staff_with_files)
            context["staff_without_files_count"] = context["total_staff"] - context["staff_with_files_count"]

        context["pending_access_requests"] = FileAccessRequest.objects.filter(
            file__in=File.objects.filter(scope_filter), status="pending"
        ).order_by("-created_at")[:5]

        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(
            self.request,
            "You do not have permission to access the executive dashboard.",
        )
        return redirect("document_management:my_files")


class FileCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = File
    form_class = FileForm
    template_name = "document_management/file_form.html"

    def test_func(self):
        user = self.request.user
        try:
            return user.staff.is_registry or user.is_superuser
        except AttributeError:
            return False

    def get_success_url(self):
        try:
            staff = self.request.user.staff
            if "registry" in staff.designation.name.lower() if staff.designation else False:
                return reverse_lazy("document_management:registry_hub")
        except Staff.DoesNotExist:
            pass
        return reverse_lazy("document_management:my_files")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        owner_id = self.request.GET.get("owner_id")
        if owner_id:
            try:
                owner = Staff.objects.get(id=owner_id)
                initial["owner"] = owner
                initial["file_type"] = "personal"
                owner_name = (
                    owner.user.get_full_name().upper() if owner.user.get_full_name() else owner.user.username.upper()
                )
                initial["title"] = f"PERSONNEL FILE OF {owner_name}"
            except Staff.DoesNotExist:
                pass
        return initial

    def form_valid(self, form):
        user_staff = self.get_staff_user()
        if not user_staff:
            raise Http404("Staff user profile not found.")

        form.instance.current_location = user_staff
        form.instance.created_by = self.request.user
        form.instance.status = "active"

        if form.cleaned_data.get("file_type") == "personal" and not form.instance.department:
            owner = form.cleaned_data.get("owner")
            if owner:
                form.instance.department = owner.department

        self.object = form.save()

        # Notify file owner (personal files) or HOD (policy files) that file is ready
        file_type = form.cleaned_data.get("file_type")
        if file_type == "personal":
            owner = form.cleaned_data.get("owner")
            if owner and owner.user:
                create_notification(
                    user=owner.user,
                    message=f"A new personal file has been created for you: {self.object.file_number} — {self.object.title}.",
                    obj=self.object,
                    link=self.object.get_absolute_url(),
                )
        elif file_type == "policy":
            dept = form.cleaned_data.get("department")
            if dept and dept.head and dept.head.user:
                create_notification(
                    user=dept.head.user,
                    message=f"A new policy file has been created in your department: {self.object.file_number} — {self.object.title}.",
                    obj=self.object,
                    link=self.object.get_absolute_url(),
                )

        for f in self.request.FILES.getlist("attachments"):
            Document.objects.create(file=self.object, attachment=f, uploaded_by=self.request.user)

        log_action(self.request.user, "FILE_CREATED", request=self.request, obj=self.object)

        messages.success(self.request, "File and documents created successfully.")
        return redirect(self.get_success_url())

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "You do not have permission to create a new file.")
        return redirect("document_management:my_files")


class MyFilesView(HTMXLoginRequiredMixin, ListView):
    model = File
    template_name = "document_management/my_files.html"
    context_object_name = "owned_folders"
    paginate_by = 10

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["document_management/partials/_my_files_list.html"]
        return [self.template_name]

    def get_queryset(self):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")

        queryset = File.objects.filter(
            Q(owner=staff_user) | Q(created_by=self.request.user) | Q(current_location=staff_user)
        ).distinct()

        if not staff_user.is_registry:
            queryset = queryset.exclude(status__in=["inactive", "closed"])

        search_query = self.request.GET.get("q")
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(file_number__icontains=search_query)
                | Q(documents__title__icontains=search_query)
            ).distinct()

            queryset = queryset.prefetch_related(
                Prefetch(
                    "documents",
                    queryset=Document.objects.filter(title__icontains=search_query),
                )
            )
        else:
            queryset = queryset.prefetch_related("documents")

        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        context = super().get_context_data(**kwargs)

        personal_folder = File.objects.filter(owner=staff_user, file_type="personal").first()
        context["staff_file_number"] = personal_folder.file_number if personal_folder else "NOT ASSIGNED"

        context["selected_search_query"] = self.request.GET.get("q", "")
        return context

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None


class MessagesView(HTMXLoginRequiredMixin, View):
    """Redirects to the new document inbox."""

    def get(self, request, *args, **kwargs):
        return redirect("document_management:inbox")


class FileRequestActivationView(LoginRequiredMixin, View):
    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        staff_user = self.get_staff_user()

        if file_obj.owner != staff_user and file_obj.created_by != request.user:
            messages.error(request, "Only the owner or creator can request activation.")
            return redirect("document_management:my_files")

        if file_obj.status != "inactive":
            messages.error(request, "Only inactive files can be submitted for activation.")
            return redirect("document_management:my_files")

        file_obj.status = "pending_activation"
        file_obj.save()

        log_action(request.user, "FILE_ACTIVATION_REQUESTED", request=request, obj=file_obj)
        messages.success(request, f"File {file_obj.file_number} has been submitted for activation.")
        return redirect("document_management:my_files")


class FileRecallView(HTMXLoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.view_file"

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        staff_user = self.get_staff_user()

        if file_obj.is_in_active_chain:
            messages.error(
                request,
                "This file is locked in an approval chain and cannot be recalled.",
            )
            return redirect(file_obj.get_absolute_url())

        if file_obj.owner != staff_user and not staff_user.is_registry:
            messages.error(request, "Only the file owner or registry staff can recall a file.")
            return redirect(file_obj.get_absolute_url())

        if file_obj.current_location == staff_user:
            messages.info(request, "File is already with you.")
            return redirect(file_obj.get_absolute_url())

        old_location = file_obj.current_location
        file_obj.current_location = None  # always returns to registry
        file_obj.status = "active"
        file_obj.save()

        FileMovement.objects.create(
            file=file_obj,
            sent_by=request.user,
            from_location=old_location,
            sent_to=None,
            action="recalled",
        )

        # Revoke all approved read & write access on recall
        revoked_count = FileAccessRequest.objects.filter(file=file_obj, status="approved").update(status="expired")

        log_action(
            request.user,
            "FILE_RECALLED",
            request=request,
            obj=file_obj,
            details={
                "from": old_location.user.get_full_name() if old_location else "Registry",
                "access_revoked": revoked_count,
            },
        )
        messages.success(
            request,
            f"File {file_obj.file_number} recalled. {revoked_count} access grant(s) revoked.",
        )
        return redirect(file_obj.get_absolute_url())

    def get_staff_user(self):
        user = self.request.user
        try:
            return Staff.objects.get(user=user)
        except Staff.DoesNotExist:
            return None


class FileDetailView(HTMXLoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = File
    template_name = "document_management/file_detail.html"
    context_object_name = "file"
    permission_required = "document_management.view_file"

    def has_permission(self):
        file_obj = self.get_object()
        user = self.request.user

        if user.is_superuser:
            return True

        staff_user = getattr(user, "staff", None)
        if not staff_user:
            return False

        if staff_user.is_registry:
            return True

        if staff_user.is_md:
            return True  # MD sees all files org-wide

        if file_obj.file_type == "policy":
            if staff_user.is_hod and file_obj.department == staff_user.department:
                return True
            if staff_user.is_unit_manager and file_obj.department == staff_user.department:
                return True

        if (
            file_obj.file_type == "personal"
            and staff_user.is_hod
            and (
                (file_obj.owner and file_obj.owner.department == staff_user.department)
                or file_obj.department == staff_user.department
            )
        ):
            return True

        if file_obj.owner == staff_user:
            # Owner can see the file page but needs an access request to view content
            return True

        if file_obj.current_location == staff_user:
            return True

        has_approved_access = (
            FileAccessRequest.objects.filter(file=file_obj, requested_by=user, status="approved")
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )

        return bool(has_approved_access)

    def _reclaim_expired_custody(self, file_obj):
        """If current custodian holds the file via an expired access request, return it to registry."""
        holder = file_obj.current_location
        if not holder or holder.is_registry:
            return
        # Check if holder is the file owner — owners always keep custody
        if file_obj.owner == holder:
            return
        # Check if holder has any active (non-expired) approved access
        active_access = (
            FileAccessRequest.objects.filter(file=file_obj, requested_by=holder.user, status="approved")
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )
        if not active_access:
            # Find any registry staff to return to
            from organization.models import Staff as StaffModel

            registry_staff = StaffModel.objects.filter(
                Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
            ).first()
            if registry_staff:
                file_obj.current_location = registry_staff
                file_obj.save(update_fields=["current_location"])

    def can_view_original(self, file, user):
        """
        Who can view actual document contents (minute_content, attachments).
        Only HODs, Supervisors, Executives, and MD.
        Registry staff and general staff cannot view document contents.
        Sensitive files enforce the same restriction regardless.
        """
        from document_management.permissions import can_view_document_content

        return can_view_document_content(user, file=file)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        file_obj = self.get_object()
        user = self.request.user

        # Return custody to registry if current holder's access has expired
        self._reclaim_expired_custody(file_obj)

        is_custodian = hasattr(user, "staff") and file_obj.current_location == user.staff

        has_approved_access = (
            FileAccessRequest.objects.filter(file=file_obj, requested_by=user, status="approved")
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )

        has_rw_access = (
            FileAccessRequest.objects.filter(
                file=file_obj,
                requested_by=user,
                status="approved",
                access_type="read_write",
            )
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )

        is_registry = hasattr(user, "staff") and user.staff.is_registry

        hasattr(user, "staff") and file_obj.owner == user.staff
        context["can_add_minute"] = (
            is_registry or (is_custodian and has_rw_access)
        ) and not file_obj.is_in_active_chain
        context["can_add_minutes"] = context["can_add_minute"]
        context["can_send_file"] = (
            (is_custodian or is_registry) and not file_obj.is_in_active_chain and file_obj.status == "active"
        )
        context["is_custodian"] = is_custodian
        context["has_approved_access"] = has_approved_access
        context["has_rw_access"] = has_rw_access
        context["access_type"] = "read_write" if has_rw_access else ("read_only" if has_approved_access else None)
        context["is_registry"] = is_registry
        context["can_view_original"] = self.can_view_original(file_obj, user)
        context["is_limited_view"] = not context["can_view_original"]
        sender_staff = getattr(user, "staff", None)
        context["send_file_form"] = SendFileForm(user=user, staff=sender_staff, file_obj=file_obj)
        context["access_request_form"] = FileAccessRequestForm()
        context["pending_access_request"] = FileAccessRequest.objects.filter(
            file=file_obj, requested_by=user, status="pending"
        ).exists()
        context["movements"] = file_obj.movements.select_related("sent_by", "from_location__user", "sent_to__user")[:20]
        # Share document permission
        from document_management.permissions import can_share_document
        context["can_share_document"] = can_share_document(user)

        # Build recipient list using central permission function
        from document_management.permissions import get_dispatch_recipients
        from organization.models import Staff as StaffModel

        recipient_qs = get_dispatch_recipients(user, file_obj)

        context["approver_choices"] = recipient_qs.order_by("user__last_name")
        context["sender_is_hod_or_above"] = sender_staff and (
            sender_staff.is_hod or sender_staff.is_md or sender_staff.is_executive
        )
        context["sender_is_supervisor"] = sender_staff and sender_staff.is_effective_supervisor
        from core.constants import STATUS_CHOICES

        context["status_choices"] = STATUS_CHOICES

        # Available chain templates for this file's department
        from django.db.models import Q as DQ

        from document_management.models import ApprovalChain, ChainTemplate

        staff_dept = getattr(getattr(user, "staff", None), "department", None)
        context["available_chain_templates"] = ChainTemplate.objects.filter(is_active=True).filter(
            DQ(department=staff_dept) | DQ(department__isnull=True)
        )

        # Active document chain (if any)
        context["is_in_active_chain"] = file_obj.is_in_active_chain
        context["active_document_chain"] = (
            ApprovalChain.objects.filter(file=file_obj, status__in=["draft", "active"])
            .select_related("document")
            .prefetch_related("steps__approver__user")
            .first()
        )

        # Build unified chronicle
        documents = list(file_obj.documents.select_related("uploaded_by").all())
        context["documents"] = documents
        audit_entries = list(
            AuditLogEntry.objects.filter(object_id=file_obj.pk, content_type__model="file")
            .select_related("user")
            .order_by("timestamp")
        )

        # Chain step activity
        from document_management.models import ApprovalStep

        chain_steps = list(
            ApprovalStep.objects.filter(
                chain__file=file_obj,
                status__in=["approved", "rejected"],
                actioned_at__isnull=False,
            )
            .select_related("approver__user", "chain__document")
            .order_by("actioned_at")
        )

        chronicle = []
        for doc in documents:
            chronicle.append({"type": "document", "item": doc, "timestamp": doc.uploaded_at})
        for entry in audit_entries:
            chronicle.append({"type": "audit", "item": entry, "timestamp": entry.timestamp})
        for step in chain_steps:
            chronicle.append({"type": "chain_step", "item": step, "timestamp": step.actioned_at})

        chronicle.sort(key=lambda x: x["timestamp"])
        context["chronicle"] = chronicle

        return context

    def post(self, request, *args, **kwargs):
        file_obj = self.get_object()
        action = request.POST.get("action")

        if action == "request_access":
            already_pending = FileAccessRequest.objects.filter(
                file=file_obj, requested_by=request.user, status="pending"
            ).exists()
            if already_pending:
                messages.warning(request, "You already have a pending access request for this file.")
            else:
                FileAccessRequest.objects.create(
                    file=file_obj,
                    requested_by=request.user,
                    access_type=request.POST.get("access_type", "read_only"),
                    reason=request.POST.get("reason", ""),
                    status="pending",
                )
                log_action(
                    request.user,
                    "ACCESS_REQUEST_SUBMITTED",
                    request=request,
                    obj=file_obj,
                )
                messages.success(request, "Access request submitted. Registry will review shortly.")
            return redirect(file_obj.get_absolute_url())

        if action == "send_file":
            staff_user = getattr(request.user, "staff", None)
            is_registry = staff_user and staff_user.is_registry

            # Block if file is in an active approval chain
            if file_obj.is_in_active_chain:
                messages.error(
                    request,
                    "This file is locked in an approval chain and cannot be moved.",
                )
                return redirect(file_obj.get_absolute_url())

            # Block if there are pending access requests on the file
            if file_obj.access_requests.filter(status="pending").exists():
                messages.error(
                    request,
                    "This file has pending access requests. Resolve them before sending.",
                )
                return redirect(file_obj.get_absolute_url())

            if file_obj.current_location != staff_user and not is_registry:
                messages.error(
                    request,
                    "Only the current custodian or registry can send this file.",
                )
                return redirect(file_obj.get_absolute_url())

            form = SendFileForm(
                request.POST,
                request.FILES,
                user=request.user,
                staff=staff_user,
                file_obj=file_obj,
            )
            if form.is_valid():
                recipient_user = form.cleaned_data["recipient"]
                try:
                    recipient = recipient_user.staff
                except Staff.DoesNotExist:
                    messages.error(request, "Selected recipient has no staff profile.")
                    return redirect(file_obj.get_absolute_url())

                # Enforce routing rules
                if not is_registry and staff_user:
                    from document_management.permissions import get_dispatch_recipients

                    allowed_recipients = get_dispatch_recipients(request.user, file_obj)
                    if not allowed_recipients.filter(pk=recipient.pk).exists():
                        if staff_user.is_hod or staff_user.is_md or staff_user.is_executive:
                            messages.error(request, "Invalid recipient selection.")
                        elif staff_user.is_effective_supervisor:
                            messages.error(request, "Supervisors can only send files to other supervisors or their direct heads.")
                        else:
                            messages.error(request, "You can only send this file to your direct head (Unit Manager or HOD).")
                        return redirect(file_obj.get_absolute_url())
                old_location = file_obj.current_location
                note = request.POST.get("movement_note", "")
                file_obj.current_location = recipient
                file_obj.status = "in_transit"
                file_obj.save()

                FileMovement.objects.create(
                    file=file_obj,
                    sent_by=request.user,
                    from_location=old_location,
                    sent_to=recipient,
                    note=note,
                    attachment=form.cleaned_data.get("movement_attachment"),
                    action="sent",
                )
                log_action(
                    request.user,
                    "FILE_SENT",
                    request=request,
                    obj=file_obj,
                    details={"to": recipient.user.get_full_name()},
                )
                create_notification(
                    user=recipient.user,
                    message=f"{request.user.get_full_name()} sent you file {file_obj.file_number} — {file_obj.title}.",
                    obj=file_obj,
                    link=file_obj.get_absolute_url(),
                )
                # Revoke sender's access to the file
                FileAccessRequest.objects.filter(file=file_obj, requested_by=request.user, status="approved").update(
                    status="expired"
                )
                messages.success(request, f"File sent to {recipient.user.get_full_name()}.")
                return redirect("document_management:my_files")

        elif action == "acknowledge_receipt":
            staff_user = getattr(request.user, "staff", None)
            if file_obj.current_location != staff_user:
                messages.error(request, "You are not the current custodian of this file.")
                return redirect(file_obj.get_absolute_url())
            if file_obj.status == "in_transit":
                file_obj.status = "active"
                file_obj.save(update_fields=["status"])
                log_action(request.user, "FILE_RECEIVED", request=request, obj=file_obj)
                messages.success(request, f"Receipt of file {file_obj.file_number} acknowledged.")
            return redirect(file_obj.get_absolute_url())

        elif action == "update_document_status":
            doc_id = request.POST.get("document_id")
            new_status = request.POST.get("status")
            status_reason = request.POST.get("status_reason", "")

            document = get_object_or_404(Document, pk=doc_id, file=file_obj)

            # Check permissions
            if document.uploaded_by != request.user and not getattr(request.user, "is_superuser", False):
                messages.error(
                    request,
                    "You do not have permission to update this document's status.",
                )
            elif new_status not in dict(Document.STATUS_CHOICES):
                messages.error(request, "Invalid status selected.")
            elif new_status == "cancelled" and not status_reason.strip():
                messages.error(request, "A reason is required when cancelling a document.")
            else:
                document.status = new_status
                document.status_reason = status_reason
                document.save()

                log_action(
                    request.user,
                    "DOCUMENT_STATUS_UPDATED",
                    request=request,
                    obj=document,
                    details={"new_status": new_status, "reason": status_reason},
                )
                messages.success(request, f"Document status updated to {new_status.title()}.")

            return redirect(file_obj.get_absolute_url())

        elif action == "update_status":
            staff = getattr(request.user, "staff", None)
            if not (request.user.is_superuser or (staff and staff.is_registry)):
                messages.error(request, "Only registry staff can update file status.")
                return redirect(file_obj.get_absolute_url())
            new_status = request.POST.get("status")
            valid = [v for v, _ in file_obj._meta.get_field("status").choices]
            if new_status not in valid:
                messages.error(request, "Invalid status.")
                return redirect(file_obj.get_absolute_url())
            file_obj.status = new_status
            file_obj.save()
            log_action(
                request.user,
                "FILE_STATUS_UPDATED",
                request=request,
                obj=file_obj,
                details={"new_status": new_status},
            )
            messages.success(request, f"File status updated to {new_status.title()}.")
            return redirect(file_obj.get_absolute_url())

        elif action == "sign_document":
            doc_id = request.POST.get("document_id")

            document = get_object_or_404(Document, pk=doc_id, file=file_obj)
            try:
                staff = request.user.staff
                active_sig = staff.get_active_signature()
                if active_sig:
                    if DocumentSignature.objects.filter(document=document, signatory=request.user).exists():
                        messages.warning(request, "You have already signed this document.")
                    else:
                        DocumentSignature.objects.create(
                            document=document,
                            signatory=request.user,
                            signature_record=active_sig,
                        )
                        log_action(
                            request.user,
                            "DOCUMENT_SIGNED",
                            request=request,
                            obj=document,
                            details={"signatory": request.user.get_full_name()},
                        )
                        messages.success(request, "Signature attached successfully.")
                else:
                    messages.warning(
                        request,
                        "You have no active signature uploaded in your profile.",
                    )

            except Exception:
                messages.error(request, "Only staff members can attach signatures.")

            return redirect(file_obj.get_absolute_url())

        elif action == "share_document":
            doc_id = request.POST.get("document_id")
            recipient_email = request.POST.get("recipient_email", "").strip()
            subject = request.POST.get("subject", "").strip()
            message = request.POST.get("message", "").strip()
            include_signature = request.POST.get("include_signature") == "on"

            from ..permissions import can_share_document
            from django.core.mail import send_mail
            from django.conf import settings

            document = get_object_or_404(Document, pk=doc_id, file=file_obj)

            # Check permission
            if not can_share_document(request.user):
                messages.error(request, "You do not have permission to share documents.")
                return redirect(file_obj.get_absolute_url())

            # Check if user has an active verified signature
            staff = getattr(request.user, "staff", None)
            if not staff:
                messages.error(request, "Staff profile not found.")
                return redirect(file_obj.get_absolute_url())

            active_signature = staff.get_active_signature()
            if not active_signature or not active_signature.is_verified:
                messages.error(request, "You need an active, verified digital signature to share documents.")
                return redirect(file_obj.get_absolute_url())

            if not recipient_email:
                messages.error(request, "Recipient email is required.")
                return redirect(file_obj.get_absolute_url())

            # Build email
            sender_name = request.user.get_full_name() or request.user.username
            file_number = file_obj.file_number

            email_subject = subject if subject else f"Shared Document: {document.title or 'Untitled'}"
            email_message = f"""
{request.POST.get("message", "").strip()}

---
Document: {document.title or 'Untitled'}
File: {file_number}
Shared by: {sender_name}
Department: {staff.department.name if staff.department else 'N/A'}
Date: {timezone.now().strftime("%B %d, %Y @ %H:%M")}

This document was shared via the Personnel Information Management System (PIMS).
"""

            # Attach signature image
            signature_attachment = None
            if include_signature and active_signature.image:
                signature_attachment = active_signature.image

            try:
                send_mail(
                    subject=email_subject,
                    message=email_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient_email],
                    fail_silently=False,
                    attachments=[(f"signature_{staff.user.username}.png", signature_attachment.read(), "image/png")] if signature_attachment else None,
                )
                messages.success(request, f"Document shared successfully with {recipient_email}.")
                log_action(
                    request.user,
                    "DOCUMENT_SHARED_EMAIL",
                    request=request,
                    obj=file_obj,
                    details={"document_id": document.pk, "recipient": recipient_email, "subject": email_subject}
                )
            except Exception as e:
                messages.error(request, f"Failed to send email: {str(e)}")

            return redirect(file_obj.get_absolute_url())

        return self.get(request, *args, **kwargs)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "You do not have permission to view this file.")
        return redirect("document_management:my_files")


class FileUpdateView(HTMXLoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = File
    form_class = FileUpdateForm
    template_name = "document_management/file_form.html"
    context_object_name = "file"

    def get_success_url(self):
        return self.object.get_absolute_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        log_action(self.request.user, "FILE_UPDATED", request=self.request, obj=self.object)
        messages.success(self.request, "File updated successfully.")
        return response

    def test_func(self):
        self.get_object()
        user = self.request.user
        return user.is_superuser or (hasattr(user, "staff") and user.staff.is_registry)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "You do not have permission to update this file.")
        return redirect(self.get_object().get_absolute_url())


class FileCloseView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        file_obj = get_object_or_404(File, pk=self.kwargs["pk"])
        user = self.request.user
        if user.is_superuser:
            return True
        staff = getattr(user, "staff", None)
        if not staff:
            return False
        return staff.is_registry or (staff.is_hod and file_obj.department == staff.department)

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)

        open_chains = file_obj.approval_chains.filter(status="active")
        if open_chains.exists():
            chain_list = ", ".join(str(c.pk) for c in open_chains)
            messages.error(
                request,
                f"Cannot close file: {open_chains.count()} active chain(s) must be "
                f"resolved first (chain IDs: {chain_list}).",
            )
            return redirect(file_obj.get_absolute_url())

        file_obj.status = "closed"
        file_obj.save()
        log_action(request.user, "FILE_CLOSED", request=request, obj=file_obj)
        messages.success(request, f"File {file_obj.file_number} has been closed.")
        return redirect(file_obj.get_absolute_url())

    def handle_no_permission(self):
        messages.error(self.request, "You do not have permission to close this file.")
        return redirect("document_management:my_files")


class FileArchiveView(HTMXLoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.archive_file"

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        file_obj.status = "archived"
        file_obj.save()

        log_action(request.user, "FILE_ARCHIVED", request=request, obj=file_obj)
        messages.success(request, f"File {file_obj.file_number} has been moved to archives.")

        if request.headers.get("HX-Request"):
            return HttpResponse(status=204, headers={"HX-Trigger": "fileArchived"})

        return redirect("document_management:registry_hub")

    def handle_no_permission(self):
        messages.error(self.request, "You do not have permission to archive files.")
        return redirect("document_management:registry_hub")


class DirectorAdminDashboardView(HTMXLoginRequiredMixin, UserPassesTestMixin, ListView):
    model = File
    template_name = "document_management/admin_dashboard.html"
    context_object_name = "recent_files"

    def test_func(self):
        return self.request.user.is_superuser

    def get_staff_user(self):
        try:
            return Staff.objects.get(user=self.request.user)
        except Staff.DoesNotExist:
            return None

    def get_queryset(self):
        return File.objects.all().order_by("-created_at")[:10]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["total_files_count"] = File.objects.count()
        context["active_files_count"] = File.objects.filter(status="active").count()
        context["pending_activation_count"] = File.objects.filter(status="pending_activation").count()
        context["archived_files_count"] = File.objects.filter(status="archived").count()

        context["total_staff_count"] = Staff.objects.count()
        context["total_departments_count"] = Department.objects.count()

        today = timezone.now().date()
        context["actions_today"] = AuditLogEntry.objects.filter(timestamp__date=today).count()
        context["recent_activities"] = AuditLogEntry.objects.select_related("user").all()[:10]

        return context

    def handle_no_permission(self):
        messages.error(self.request, "Only directors/superusers can access the admin dashboard.")
        return redirect("document_management:my_files")


class FileDeleteView(HTMXLoginRequiredMixin, UserPassesTestMixin, View):
    """Delete a file (folder) container. Only Registry or Superusers can delete files."""

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        try:
            return user.staff.is_registry
        except AttributeError:
            return False

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        file_number = file_obj.file_number

        log_action(
            request.user,
            "FILE_DELETED",
            request=request,
            details={"file_number": file_number, "title": file_obj.title},
        )

        file_obj.delete()
        messages.success(request, f"File {file_number} deleted successfully.")
        return redirect("document_management:registry_hub")


class RecordExplorerView(HTMXLoginRequiredMixin, UserPassesTestMixin, ListView):
    model = File
    template_name = "document_management/record_explorer.html"
    context_object_name = "files"
    paginate_by = 20

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        staff = getattr(user, "staff", None)
        return staff and (staff.is_registry or staff.is_hod or staff.is_unit_manager or staff.is_md)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "You do not have permission to access the Record Explorer.")
        return redirect("document_management:my_files")

    def get_queryset(self):
        staff = getattr(self.request.user, "staff", None)
        queryset = File.objects.filter(status="active").order_by("file_number")

        # HODs see only their department's files (policy + personal), excluding their own
        # MD sees everything
        if staff and staff.is_hod and not staff.is_md and not staff.is_registry and not self.request.user.is_superuser:
            dept = staff.department
            queryset = (
                queryset.filter(Q(department=dept) | Q(file_type="personal", owner__department=dept))
                .exclude(file_type="personal", owner=staff)
                .distinct()
            )

        q = self.request.GET.get("q")
        if q:
            queryset = queryset.filter(
                Q(file_number__icontains=q) | Q(title__icontains=q) | Q(department__name__icontains=q)
            )

        dept_filter = self.request.GET.get("department")
        if dept_filter:
            queryset = queryset.filter(department_id=dept_filter)

        file_type_filter = self.request.GET.get("file_type")
        if file_type_filter:
            queryset = queryset.filter(file_type=file_type_filter)

        return queryset

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            target = self.request.headers.get("HX-Target", "")
            if target == "file-detail-content":
                return ["document_management/partials/_explorer_file_detail.html"]
            return ["document_management/partials/_explorer_sidebar_list.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["departments"] = Department.objects.all().order_by("name")
        context["selected_dept"] = self.request.GET.get("department", "")
        context["selected_file_type"] = self.request.GET.get("file_type", "")
        context["selected_search_query"] = self.request.GET.get("q", "")
        context["q"] = self.request.GET.get("q", "")

        file_pk = self.request.GET.get("file_pk")
        if file_pk:
            try:
                selected_file = File.objects.get(pk=file_pk)
                latest_docs = selected_file.documents.order_by("-uploaded_at")
                documents = latest_docs[:10]
                context["selected_file"] = selected_file
                context["documents"] = documents
                context["has_more_documents"] = latest_docs.count() > 10
            except File.DoesNotExist:
                pass

        return context

    def get_staff_user(self):
        try:
            return Staff.objects.get(user=self.request.user)
        except Staff.DoesNotExist:
            return None


def _get_allowed_forward_pks(staff):
    """Return set of allowed recipient PKs for forwarding, mirroring send-file routing rules.
    Returns None for MD/Executive (unrestricted)."""
    from organization.models import Department as Dept
    from organization.models import Unit

    base_qs = Staff.objects.exclude(
        Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
    )
    if staff.is_md or staff.is_executive:
        return None  # unrestricted
    if staff.is_hod or staff.is_head_of_unit:
        # Any HOD, any head of unit, any supervisor
        pks = set()
        for d in Dept.objects.filter(head__isnull=False):
            pks.add(d.head.pk)
        for u in Unit.objects.filter(head__isnull=False):
            pks.add(u.head.pk)
        for s in base_qs.filter(is_supervisor=True):
            pks.add(s.pk)
        pks.discard(staff.pk)
        return pks
    if staff.is_supervisor:
        pks = set()
        for d in Dept.objects.filter(head__isnull=False):
            pks.add(d.head.pk)
        for u in Unit.objects.filter(head__isnull=False):
            pks.add(u.head.pk)
        return pks
    # Regular staff
    pks = set()
    if staff.unit and staff.unit.head:
        pks.add(staff.unit.head.pk)
    elif staff.department and staff.department.head:
        pks.add(staff.department.head.pk)
    return pks


class InboxView(HTMXLoginRequiredMixin, ListView):
    """Shows all pending FileMovements sent to the current staff member.
    Supports 'urgent' mode to show urgent/high priority documents needing attention.
    """

    model = FileMovement
    template_name = "document_management/inbox.html"
    context_object_name = "movements"
    paginate_by = 15

    def get_queryset(self):
        staff = getattr(self.request.user, "staff", None)
        if not staff:
            return FileMovement.objects.none()

        mode = self.request.GET.get("mode", "inbox")

        if mode == "urgent":
            # Show urgent/high priority documents in active files that need attention
            # These are documents with priority != normal that are in active files
            # and the user has permission to view (custodian, approver, HOD, etc.)
            from ..models import Document
            from ..permissions import can_view_document_content

            # Get active files where user has access
            user_files = File.objects.filter(
                Q(current_location=staff) |
                Q(owner=staff) |
                Q(department=staff.department) if staff.department else Q(),
                status="active"
            ).distinct()

            # Get urgent/high priority documents in those files
            urgent_docs = Document.objects.filter(
                file__in=user_files,
                priority__in=["urgent", "high"],
                status__in=["pending", "in_transit"]
            ).select_related("file", "uploaded_by").order_by(
                "-priority", "-uploaded_at"
            )

            # Convert to a pseudo-movement queryset for template compatibility
            # We'll handle this in the template with a different context variable
            return FileMovement.objects.none()

        # Default inbox: movements sent to this user
        return (
            FileMovement.objects.filter(sent_to=staff, action="sent")
            .select_related("file", "document", "sent_by", "from_location__user")
            .order_by("-moved_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = getattr(self.request.user, "staff", None)
        context["can_approve"] = bool(staff and (staff.is_hod or staff.is_effective_supervisor))
        context["current_mode"] = self.request.GET.get("mode", "inbox")

        # For unit managers: pre-fill their HOD as the only forward recipient
        prefilled_recipient = None
        if staff and staff.is_head_of_unit and not (staff.is_hod or staff.is_md or staff.is_executive):
            dept = staff.department
            if dept and dept.head:
                prefilled_recipient = dept.head
        context["prefilled_recipient"] = prefilled_recipient

        # Urgent mode: fetch urgent documents
        if context["current_mode"] == "urgent" and staff:
            from ..models import Document
            user_files = File.objects.filter(
                Q(current_location=staff) |
                Q(owner=staff) |
                (Q(department=staff.department) if staff.department else Q()),
                status="active"
            ).distinct()

            # Include standalone urgent documents (file=None) that user can see
            # Plus urgent documents in accessible files
            context["urgent_documents"] = Document.objects.filter(
                Q(file__in=user_files) | Q(file__isnull=True),
                priority__in=["urgent", "high"],
                status__in=["pending", "in_transit"]
            ).select_related("file", "uploaded_by").order_by("-priority", "-uploaded_at")[:50]

        return context


class OutboxView(HTMXLoginRequiredMixin, ListView):
    """Shows all FileMovements sent by the current staff member."""

    model = FileMovement
    template_name = "document_management/outbox.html"
    context_object_name = "movements"
    paginate_by = 15

    def get_queryset(self):
        staff = getattr(self.request.user, "staff", None)
        if not staff:
            return FileMovement.objects.none()
        qs = (
            FileMovement.objects.filter(sent_by=self.request.user, action="sent")
            .select_related("file", "document", "sent_to__user", "sent_to__designation", "sent_to__department", "sent_to__unit")
            .order_by("-moved_at")
        )

        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(
                Q(file__file_number__icontains=q)
                | Q(file__title__icontains=q)
                | Q(document__title__icontains=q)
                | Q(sent_to__user__first_name__icontains=q)
                | Q(sent_to__user__last_name__icontains=q)
            )

        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_search_query"] = self.request.GET.get("q", "")
        context["selected_status"] = self.request.GET.get("status", "")
        return context


class OutboxView(HTMXLoginRequiredMixin, ListView):
    """Shows all FileMovements sent by the current staff member."""

    model = FileMovement
    template_name = "document_management/outbox.html"
    context_object_name = "movements"
    paginate_by = 15

    def get_queryset(self):
        staff = getattr(self.request.user, "staff", None)
        if not staff:
            return FileMovement.objects.none()
        return (
            FileMovement.objects.filter(sent_by=self.request.user, action="sent")
            .select_related("file", "document", "sent_to__user", "from_location__user")
            .order_by("-moved_at")
        )


class InboxRefDocView(HTMXLoginRequiredMixin, View):
    """Read-only view of a single reference document shared with the inbox recipient."""

    def get(self, request, pk):
        from document_management.models import Document

        from ..permissions import can_view_document_content

        doc = get_object_or_404(Document, pk=pk)
        # Must be shared with this user
        if not doc.shared_with.filter(pk=request.user.pk).exists():
            messages.error(request, "You do not have access to this document.")
            return redirect("document_management:inbox")

        can_view_content = can_view_document_content(request.user)

        return render(
            request,
            "document_management/inbox_ref_doc.html",
            {
                "document": doc,
                "can_view_content": can_view_content,
            },
        )


class InboxFileView(HTMXLoginRequiredMixin, View):
    """Read-only view of the file sent via a movement — shows all documents and reference files."""

    def get(self, request, pk):
        from ..permissions import can_view_document_content

        movement = get_object_or_404(FileMovement, pk=pk)
        staff = getattr(request.user, "staff", None)

        # Allow access if user is the recipient OR the sender
        is_recipient = staff and movement.sent_to == staff
        is_sender = movement.sent_by == request.user

        if not (is_recipient or is_sender):
            messages.error(request, "You do not have access to this file.")
            return redirect("document_management:inbox")

        file_obj = movement.file
        all_documents = file_obj.documents.order_by("-uploaded_at")

        # Reference documents shared with this user for this movement
        reference_docs = (
            file_obj.documents.filter(shared_with=request.user)
            .exclude(pk=movement.document.pk if movement.document else None)
            .order_by("-uploaded_at")
        )

        can_view_content = can_view_document_content(request.user)

        return render(
            request,
            "document_management/inbox_file_view.html",
            {
                "movement": movement,
                "file": file_obj,
                "all_documents": all_documents,
                "reference_docs": reference_docs,
                "can_view_content": can_view_content,
            },
        )


class InboxDocumentDetailView(HTMXLoginRequiredMixin, View):
    """Detail view for a document received via FileMovement — shows movement
    context, sender info, references, other docs."""

    def get(self, request, pk):
        from ..permissions import can_view_document_content

        movement = get_object_or_404(FileMovement, pk=pk)
        staff = getattr(request.user, "staff", None)

        # Allow access if user is the recipient OR the sender
        is_recipient = staff and movement.sent_to == staff
        is_sender = movement.sent_by == request.user

        if not (is_recipient or is_sender):
            messages.error(request, "You do not have access to this document.")
            return redirect("document_management:inbox")

        file_obj = movement.file
        document = movement.document

        # If no specific document, redirect to file view
        if not document:
            return redirect("document_management:inbox_file_view", pk=movement.pk)

        # Sender staff profile
        try:
            sender_staff = movement.sent_by.staff
        except Exception:
            sender_staff = None

        # Other documents in the same file (excluding the current one)
        other_docs = file_obj.documents.exclude(pk=document.pk).order_by("-uploaded_at")[:10]

        # Reference documents shared with the recipient for this movement
        reference_docs = (
            file_obj.documents.filter(shared_with=request.user).exclude(pk=document.pk).order_by("-uploaded_at")
        )

        # All movements for this specific document, oldest first — for chat thread
        movement_history = (
            FileMovement.objects.filter(document=document)
            .select_related("sent_by", "sent_to__user", "from_location__user")
            .order_by("moved_at")
        )

        # Full file movement history (all documents), newest first
        file_movement_history = file_obj.movements.select_related(
            "sent_by", "sent_to__user", "from_location__user", "document"
        ).order_by("-moved_at")

        can_view_content = can_view_document_content(request.user)

        return render(
            request,
            "document_management/inbox_document_detail.html",
            {
                "movement": movement,
                "document": document,
                "file": file_obj,
                "sender_staff": sender_staff,
                "other_docs": other_docs,
                "reference_docs": reference_docs,
                "movement_history": movement_history,
                "file_movement_history": file_movement_history,
                "can_view_content": can_view_content,
                "can_approve": bool(staff and (staff.is_hod or staff.is_effective_supervisor)),
                "prefilled_recipient": None,
            },
        )


class DocumentActionView(HTMXLoginRequiredMixin, View):
    """Approve or reject a document received via FileMovement.

    - HOD/Supervisor: Approve (final) or Reject (with note)
    - Unit Manager: Approve = forward to HOD (note optional), Reject = return to sender (note required)
    - Reject always requires a note
    """

    def post(self, request, pk):
        movement = get_object_or_404(FileMovement, pk=pk)
        staff = getattr(request.user, "staff", None)

        if movement.sent_to != staff:
            messages.error(request, "This document was not sent to you.")
            return redirect("document_management:inbox")

        if movement.status != "pending":
            messages.error(request, "This document has already been actioned.")
            return redirect("document_management:inbox")

        # Prevent the document creator from approving/rejecting their own document
        if movement.document and movement.document.uploaded_by == request.user:
            messages.error(request, "You cannot approve or reject your own document.")
            return redirect("document_management:inbox")

        action = request.POST.get("action")
        note = request.POST.get("note", "").strip()

        is_hod = staff.is_hod or staff.is_effective_supervisor
        is_unit_manager = staff.is_unit_manager and not (staff.is_hod or staff.is_effective_supervisor)

        if action == "approve":
            if not staff or not (staff.is_hod or staff.is_effective_supervisor or staff.is_unit_manager):
                messages.error(request, "Only HODs, supervisors, and unit managers can approve documents.")
                return redirect("document_management:inbox")

            is_hod = staff.is_hod or staff.is_effective_supervisor
            is_unit_manager = staff.is_unit_manager and not (staff.is_hod or staff.is_effective_supervisor)

            if is_hod:
                # HOD/Supervisor: Final approval
                movement.status = "approved"
                movement.save(update_fields=["status"])
                if movement.document:
                    movement.document.status = "approved"
                    movement.document.save(update_fields=["status"])
                # Transfer custody back to registry and mark file active
                from django.db.models import Q as DQ
                from organization.models import Staff as StaffModel

                registry = StaffModel.objects.filter(
                    DQ(designation__name__icontains="registry") | DQ(user__groups__name__iexact="Registry")
                ).first()
                movement.file.current_location = registry
                movement.file.status = "active"
                movement.file.save(update_fields=["current_location", "status"])
                sender_name = request.user.get_full_name() or request.user.username
                doc_ref = movement.document or movement.file.file_number
                create_notification(
                    user=movement.sent_by,
                    message=f"{sender_name} approved document '{doc_ref}'.",
                    obj=movement.file,
                    link=movement.file.get_absolute_url(),
                )
                log_action(
                    request.user,
                    "DOCUMENT_APPROVED",
                    request=request,
                    obj=movement.file,
                    details={
                        "document": str(movement.document),
                        "file": movement.file.file_number,
                        "note": note,
                        "approver_role": "HOD/Supervisor",
                    },
                )
                messages.success(request, "Document approved.")

            elif staff.is_unit_manager and not (staff.is_hod or staff.is_effective_supervisor):
                # Unit Manager: "Approve" = forward to HOD (note optional)
                from organization.models import Staff as StaffModel
                from django.db.models import Q as DQ

                hod = StaffModel.objects.filter(
                    department=staff.department,
                    is_hod=True
                ).first()

                if not hod:
                    messages.error(request, "No HOD found for your department.")
                    return redirect("document_management:inbox")

                movement.status = "forwarded"
                movement.save(update_fields=["status"])
                FileMovement.objects.create(
                    file=movement.file,
                    document=movement.document,
                    sent_by=request.user,
                    from_location=staff,
                    sent_to=hod,
                    note=note,
                    action="sent",
                )
                movement.file.current_location = hod
                movement.file.save(update_fields=["current_location"])
                sender_name = request.user.get_full_name() or request.user.username
                doc_ref = movement.document or movement.file.file_number
                create_notification(
                    user=hod.user,
                    message=f"{sender_name} forwarded document '{doc_ref}' to you for approval.",
                    obj=movement.file,
                    link=reverse_lazy("document_management:inbox"),
                )
                log_action(
                    request.user,
                    "DOCUMENT_FORWARDED_TO_HOD",
                    request=request,
                    obj=movement.file,
                    details={
                        "document": str(movement.document),
                        "file": movement.file.file_number,
                        "to_hod": hod.user.get_full_name(),
                        "note": note,
                    },
                )
                messages.success(request, f"Document forwarded to HOD ({hod.user.get_full_name()}).")

        elif action == "reject":
            if not staff or not (staff.is_hod or staff.is_effective_supervisor or staff.is_unit_manager):
                messages.error(request, "Only HODs, supervisors, and unit managers can reject documents.")
                return redirect("document_management:inbox")

            if not note:
                messages.error(request, "A reason is required when rejecting a document.")
                return redirect("document_management:inbox")

            movement.status = "rejected"
            movement.save(update_fields=["status"])
            if movement.document:
                movement.document.status = "rejected"
                movement.document.save(update_fields=["status"])
            try:
                sender_staff = movement.sent_by.staff
                movement.file.current_location = sender_staff
                movement.file.status = "active"
                movement.file.save(update_fields=["current_location", "status"])
            except Exception:
                pass
            sender_name = request.user.get_full_name() or request.user.username
            doc_ref = movement.document or movement.file.file_number
            create_notification(
                user=movement.sent_by,
                message=(f"{sender_name} rejected document '{doc_ref}'. Note: {note}"),
                obj=movement.file,
                link=movement.file.get_absolute_url(),
            )
            log_action(
                request.user,
                "DOCUMENT_REJECTED",
                request=request,
                obj=movement.file,
                details={
                    "document": str(movement.document),
                    "file": movement.file.file_number,
                    "note": note,
                    "rejector_role": "HOD/Supervisor" if staff.is_hod or staff.is_effective_supervisor else "Unit Manager",
                },
            )
            messages.warning(request, "Document rejected and returned to sender.")

        else:
            messages.error(request, "Invalid action.")

        return redirect("document_management:inbox")


class FileBatchUploadView(LoginRequiredMixin, UserPassesTestMixin, View):
    template_name = "document_management/file_batch_upload.html"

    def test_func(self):
        try:
            return self.request.user.staff.is_registry or self.request.user.is_superuser
        except AttributeError:
            return False

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "Only registry staff can perform batch uploads.")
        return redirect("document_management:registry_hub")

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        import csv
        import io

        from django.db import transaction

        csv_file = request.FILES.get("csv_file")
        if not csv_file:
            messages.error(request, "Please select a CSV file to upload.")
            return render(request, self.template_name)

        if not csv_file.name.endswith(".csv"):
            messages.error(request, "The uploaded file is not a CSV.")
            return render(request, self.template_name)

        try:
            decoded_file = csv_file.read().decode("utf-8")
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)
        except Exception as e:
            messages.error(request, f"Failed to read CSV: {e!s}")
            return render(request, self.template_name)

        required_cols = ["title", "file_type"]
        if not reader.fieldnames or not all(c in reader.fieldnames for c in required_cols):
            missing = [c for c in required_cols if not reader.fieldnames or c not in reader.fieldnames]
            messages.error(request, f"CSV is missing required columns: {', '.join(missing)}")
            return render(request, self.template_name)

        results = {"success": [], "errors": []}
        registry_staff = request.user.staff

        for row_idx, row in enumerate(reader, start=2):
            try:
                with transaction.atomic():
                    file_type = row["file_type"].strip().lower()
                    title = row["title"].strip().upper()

                    if file_type not in ("personal", "policy"):
                        raise ValueError(f'Invalid file_type "{file_type}". Must be "personal" or "policy".')

                    kwargs_create = {
                        "title": title,
                        "file_type": file_type,
                        "current_location": registry_staff,
                        "created_by": request.user,
                    }

                    if file_type == "personal":
                        owner_username = row.get("owner_username", "").strip()
                        if not owner_username:
                            raise ValueError("owner_username is required for personal files.")
                        from organization.models import Staff as StaffModel

                        try:
                            owner = StaffModel.objects.get(user__username=owner_username)
                        except StaffModel.DoesNotExist:
                            raise ValueError(f'Staff with username "{owner_username}" not found.') from None
                        kwargs_create["owner"] = owner
                        kwargs_create["department"] = owner.department

                    elif file_type == "policy":
                        policy_range = row.get("policy_range", "internal").strip().lower()
                        if policy_range == "internal":
                            dept_code = row.get("department_code", "").strip()
                            if not dept_code:
                                raise ValueError("department_code is required for internal policy files.")
                            from organization.models import Department as DeptModel
                            from organization.models import Unit as UnitModel

                            dept = DeptModel.objects.filter(code=dept_code).first()
                            if not dept:
                                raise ValueError(f'Department code "{dept_code}" not found.')
                            kwargs_create["department"] = dept
                            unit_name = row.get("unit_name", "").strip()
                            if unit_name:
                                unit = UnitModel.objects.filter(name=unit_name, department=dept).first()
                                if not unit:
                                    raise ValueError(f'Unit "{unit_name}" not found in department "{dept.name}".')
                                kwargs_create["unit"] = unit
                        else:
                            external_party = row.get("external_party", "").strip()
                            if not external_party:
                                raise ValueError("external_party is required for external policy files.")
                            kwargs_create["external_party"] = external_party

                    file_obj = File.objects.create(**kwargs_create)
                    results["success"].append(f'File "{file_obj.file_number} - {title}" created.')
                    log_action(
                        request.user,
                        "FILE_CREATED_BATCH",
                        request=request,
                        obj=file_obj,
                        details={"file_number": file_obj.file_number, "batch": True},
                    )

            except Exception as e:
                results["errors"].append(f"Row {row_idx}: {e!s}")

        return render(request, self.template_name, {"results": results})


class DownloadSampleFileCSVView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        try:
            return self.request.user.staff.is_registry or self.request.user.is_superuser
        except AttributeError:
            return False

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "Only registry staff can download sample CSV.")
        return redirect("document_management:registry_hub")

    def get(self, request, *args, **kwargs):
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="sample_files.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["title", "file_type", "owner_username", "department_code", "unit_name", "policy_range", "external_party"]
        )
        writer.writerow(["PERSONNEL FILE OF JOHN DOE", "personal", "john.doe", "", "", "", ""])
        writer.writerow(["LEAVE POLICY 2025", "policy", "", "HR001", "Recruitment Unit", "internal", ""])
        writer.writerow(["MOU WITH WHO", "policy", "", "", "", "external", "World Health Organization"])
        return response


class FileCreationApprovalView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    View for file owner (personal files) or HOD (policy files) to approve/reject
    a newly created file with their digital signature.
    """
    model = File
    template_name = "document_management/file_creation_approval.html"
    context_object_name = "file"

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        try:
            staff = user.staff
        except AttributeError:
            return False
        
        file_obj = self.get_object()
        
        # Personal files: only the owner can approve
        if file_obj.file_type == "personal":
            return file_obj.owner == staff
        
        # Policy files: only the HOD of the department can approve
        if file_obj.file_type == "policy":
            return staff.is_hod and file_obj.department == staff.department
        
        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        file_obj = self.get_object()
        
        # Get the user's active signature
        try:
            active_signature = self.request.user.staff.get_active_signature()
            context["active_signature"] = active_signature
        except Exception:
            context["active_signature"] = None
        
        return context

    def post(self, request, *args, **kwargs):
        file_obj = self.get_object()
        staff = getattr(request.user, "staff", None)
        
        if not staff:
            messages.error(request, "Staff profile not found.")
            return redirect(file_obj.get_absolute_url())
        
        # Verify permission
        if not self.test_func():
            messages.error(request, "You do not have permission to approve this file.")
            return redirect(file_obj.get_absolute_url())
        
        # Check if user has active verified signature
        active_signature = staff.get_active_signature()
        if not active_signature or not active_signature.is_verified:
            messages.error(request, "You need an active, verified digital signature to approve this file.")
            return redirect(file_obj.get_absolute_url())
        
        action = request.POST.get("action")
        
        if action == "approve":
            # Approve the file - change status to pending_activation for registry
            file_obj.status = "pending_activation"
            file_obj.current_location = staff
            file_obj.save(update_fields=["status", "current_location"])
            
            log_action(
                request.user,
                "FILE_CREATION_APPROVED",
                request=request,
                obj=file_obj,
                details={
                    "approver": staff.user.get_full_name(),
                    "signature_id": active_signature.pk,
                }
            )
            
            # Notify registry staff
            registry_staff = Staff.objects.filter(
                Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
            ).select_related("user")
            
            for reg_staff in registry_staff:
                if reg_staff.user:
                    create_notification(
                        user=reg_staff.user,
                        message=f"File {file_obj.file_number} — {file_obj.title} has been approved by {staff.user.get_full_name()}. Ready for activation.",
                        obj=file_obj,
                        link=file_obj.get_absolute_url(),
                        send_email=True,
                        email_template="emails/file_creation_approved.html",
                        email_context={
                            "file": file_obj,
                            "approver": staff,
                            "approved_at": timezone.now(),
                        },
                        email_subject=f"File Creation Approved: {file_obj.file_number}",
                    )
            
            # Notify the creator
            if file_obj.created_by:
                create_notification(
                    user=file_obj.created_by,
                    message=f"File {file_obj.file_number} — {file_obj.title} has been approved. Status: Pending Activation.",
                    obj=file_obj,
                    link=file_obj.get_absolute_url(),
                    send_email=True,
                    email_template="emails/file_creation_approved.html",
                    email_context={
                        "file": file_obj,
                        "approver": staff,
                        "approved_at": timezone.now(),
                    },
                    email_subject=f"File Creation Approved: {file_obj.file_number}",
                )
            
            messages.success(request, "File creation approved successfully. File is now pending activation by registry.")
            
        elif action == "reject":
            rejection_reason = request.POST.get("rejection_reason", "").strip()
            if not rejection_reason:
                messages.error(request, "Rejection reason is required.")
                return redirect(request.path)
            
            # Reject the file - mark as inactive
            file_obj.status = "inactive"
            file_obj.save(update_fields=["status"])
            
            log_action(
                request.user,
                "FILE_CREATION_REJECTED",
                request=request,
                obj=file_obj,
                details={
                    "approver": staff.user.get_full_name(),
                    "reason": rejection_reason,
                }
            )
            
            # Notify the creator
            if file_obj.created_by:
                create_notification(
                    user=file_obj.created_by,
                    message=f"File {file_obj.file_number} — {file_obj.title} was rejected by {staff.user.get_full_name()}. Reason: {rejection_reason}",
                    obj=file_obj,
                    link=file_obj.get_absolute_url(),
                    send_email=True,
                    email_template="emails/file_creation_rejected.html",
                    email_context={
                        "file": file_obj,
                        "rejector": staff,
                        "rejected_at": timezone.now(),
                        "rejection_reason": rejection_reason,
                    },
                    email_subject=f"File Creation Rejected: {file_obj.file_number}",
                )
            
            messages.warning(request, "File creation rejected.")
        
        return redirect(file_obj.get_absolute_url())

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "You do not have permission to approve this file.")
        return redirect("document_management:my_files")


class DocumentDispatchApprovalView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """
    View for HOD (policy files) or Owner (personal files) to approve/reject
    a dispatched document with their digital signature.
    """
    model = Document
    template_name = "document_management/document_dispatch_approval.html"
    context_object_name = "document"

    def test_func(self):
        user = self.request.user
        if user.is_superuser:
            return True
        try:
            staff = user.staff
        except AttributeError:
            return False

        doc = self.get_object()
        file_obj = doc.file

        # Personal files: only the owner can approve
        if file_obj.file_type == "personal":
            return file_obj.owner == staff

        # Policy files: only the HOD of the department can approve
        if file_obj.file_type == "policy":
            return staff.is_hod and file_obj.department == staff.department

        return False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        doc = self.get_object()
        context["file"] = doc.file

        try:
            active_signature = self.request.user.staff.get_active_signature()
            context["active_signature"] = active_signature
        except Exception:
            context["active_signature"] = None

        return context

    def post(self, request, *args, **kwargs):
        doc = self.get_object()
        file_obj = doc.file
        staff = getattr(request.user, "staff", None)

        if not staff:
            messages.error(request, "Staff profile not found.")
            return redirect(file_obj.get_absolute_url())

        if not self.test_func():
            messages.error(request, "You do not have permission to approve this document.")
            return redirect(file_obj.get_absolute_url())

        active_signature = staff.get_active_signature()
        if not active_signature or not active_signature.is_verified:
            messages.error(request, "You need an active, verified digital signature to approve this document.")
            return redirect(file_obj.get_absolute_url())

        action = request.POST.get("action")

        if action == "approve":
            doc.status = "approved"
            doc.has_signature = True
            doc.signature_record = active_signature
            doc.status_reason = request.POST.get("note", "")
            doc.save(update_fields=["status", "has_signature", "signature_record", "status_reason"])

            # Record the signature
            DocumentSignature.objects.create(
                document=doc,
                signatory=request.user,
                signature_record=active_signature,
                ip_address=request.META.get("REMOTE_ADDR"),
                note=request.POST.get("note", ""),
            )

            # Return file to registry
            from django.db.models import Q as DQ
            from organization.models import Staff as StaffModel

            registry = StaffModel.objects.filter(
                DQ(designation__name__icontains="registry") | DQ(user__groups__name__iexact="Registry")
            ).first()
            file_obj.current_location = registry
            file_obj.status = "active"
            file_obj.save(update_fields=["current_location", "status"])

            # Find and close any active movement for this document
            active_movement = FileMovement.objects.filter(
                file=file_obj, document=doc, status="pending"
            ).first()
            if active_movement:
                active_movement.status = "approved"
                active_movement.save(update_fields=["status"])

            log_action(
                request.user,
                "DOCUMENT_APPROVED",
                request=request,
                obj=file_obj,
                details={
                    "document": str(doc),
                    "file": file_obj.file_number,
                    "approver": staff.user.get_full_name(),
                },
            )

            # Notify the sender
            if active_movement and active_movement.sent_by:
                create_notification(
                    user=active_movement.sent_by,
                    message=f"{staff.user.get_full_name()} approved document '{doc.title or 'Untitled'}' in file {file_obj.file_number}.",
                    obj=file_obj,
                    link=file_obj.get_absolute_url(),
                )

            messages.success(request, "Document approved successfully. File returned to registry.")

        elif action == "reject":
            rejection_reason = request.POST.get("rejection_reason", "").strip()
            if not rejection_reason:
                messages.error(request, "Rejection reason is required.")
                return redirect(request.path)

            doc.status = "rejected"
            doc.status_reason = rejection_reason
            doc.save(update_fields=["status", "status_reason"])

            # Return file to sender
            active_movement = FileMovement.objects.filter(
                file=file_obj, document=doc, status="pending"
            ).first()
            if active_movement:
                active_movement.status = "rejected"
                active_movement.save(update_fields=["status"])

                file_obj.current_location = active_movement.from_location
                file_obj.status = "active"
                file_obj.save(update_fields=["current_location", "status"])

                # Notify the sender
                create_notification(
                    user=active_movement.sent_by,
                    message=(
                        f"{staff.user.get_full_name()} rejected document '{doc.title or 'Untitled'}' "
                        f"in file {file_obj.file_number}. Reason: {rejection_reason}"
                    ),
                    obj=file_obj,
                    link=file_obj.get_absolute_url(),
                )

            log_action(
                request.user,
                "DOCUMENT_REJECTED",
                request=request,
                obj=file_obj,
                details={
                    "document": str(doc),
                    "file": file_obj.file_number,
                    "reason": rejection_reason,
                },
            )

            messages.warning(request, "Document rejected and returned to sender.")

        return redirect(file_obj.get_absolute_url())

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, "You do not have permission to approve this document.")
        return redirect("document_management:my_files")
