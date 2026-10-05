from datetime import timedelta
import logging

from audit_log.models import AuditLogEntry
from audit_log.utils import log_action
from core.constants import LIVE_FILE_STATUSES
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
from ..permissions import can_add_document, get_dispatch_recipients
from .base import EXCLUDE_REGISTRY_Q, HTMXLoginRequiredMixin, inbox_action_response

logger = logging.getLogger("document_management")


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
        context["closed_files"] = File.objects.filter(scope_filter, status="closed").count()
        context["archived_files"] = File.objects.filter(scope_filter, status="archived").count()

        context["personal_files_count"] = File.objects.filter(scope_filter, file_type="personal").count()
        context["policy_files_count"] = File.objects.filter(scope_filter, file_type="policy").count()

        registry_staff_ids = Staff.objects.filter(
            Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
        ).values_list("id", flat=True)

        outgoing_files = (
            File.objects.filter(scope_filter, status__in=LIVE_FILE_STATUSES)
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
                return reverse_lazy("document_management:staff_folder_list")
        except Staff.DoesNotExist:
            pass
        return reverse_lazy("document_management:my_files")

    def get(self, request, *args, **kwargs):
        # HTMX dispatch-recipient search for the create modal:
        # /documents/create/?dispatch_search=1&q=... returns option rows
        # calling selectDispatchStaff(staff_pk, name).
        if request.headers.get("HX-Request") and request.GET.get("dispatch_search"):
            return self._dispatch_recipient_options(request)
        if request.headers.get("HX-Request") and (
            request.GET.get("file_type") or request.GET.get("owner") or request.GET.get("department")
        ) and not request.GET.get("q"):
            # Legacy auto-preview hook — no longer used (dispatch is now
            # optional via modal). Return empty so old HTMX triggers no-op.
            return HttpResponse("")
        return super().get(request, *args, **kwargs)

    def _dispatch_recipient_options(self, request):
        from django.db.models import Q

        query = request.GET.get("q", "").strip()
        selected = (request.GET.get("dispatch_to") or request.GET.get("selected") or "").strip()
        eligible = get_dispatch_recipients(request.user, File(file_type="personal", title="TEMP"))
        if query and len(query) >= 1:
            eligible = eligible.filter(
                Q(department__name__icontains=query) | Q(unit__name__icontains=query)
            ).distinct()[:10]
        else:
            eligible = eligible[:10]
        if not eligible:
            return HttpResponse(
                '<div class="p-4 text-center text-sm text-slate-400">No eligible recipients found.</div>'
            )
        html = '<div class="divide-y divide-slate-100">'
        for staff in eligible:
            first = (staff.user.first_name or "").strip()
            last = (staff.user.last_name or "").strip()
            full = f"{first} {last}".strip() or staff.user.username
            name = staff.user.get_full_name() or full
            safe = name.replace("'", "\\'")
            meta = staff.role_label
            safe_meta = meta.replace("'", "\\'")
            is_selected = bool(selected) and str(staff.pk) == str(selected)
            row_cls = (
                "flex items-center justify-between px-4 py-3 cursor-pointer "
                + ("bg-nigeria-green/10 border-l-4 border-nigeria-green" if is_selected else "hover:bg-slate-50")
            )
            btn = (
                '<span class="ml-3 inline-flex items-center gap-1 px-3 py-1.5 bg-green-50 border border-green-200 '
                'text-green-800 text-[10px] font-black uppercase rounded-lg">✓ Selected</span>'
                if is_selected
                else f'<button type="button" class="ml-3 px-3 py-1.5 bg-nigeria-green text-white '
                f'text-[10px] font-black uppercase rounded-lg" '
                f'onclick="selectDispatchStaff(\'{staff.pk}\', \'{safe}\', \'{safe_meta}\')">Select</button>'
            )
            html += (
                f'<div class="{row_cls}">'
                f'<div class="min-w-0"><p class="text-sm font-bold text-slate-900">{name}</p>'
                f'<p class="text-[10px] text-slate-500 font-medium">{meta}</p></div>'
                f"{btn}</div>"
            )
        html += "</div>"
        return HttpResponse(html)

    def _get_recipient_preview(self, request):
        staff_user = self.get_staff_user()
        if not staff_user:
            return HttpResponse('<p class="text-sm text-slate-500">Unable to determine recipient.</p>')

        file_type = request.GET.get("file_type", "personal")
        owner_id = request.GET.get("owner")
        department_id = request.GET.get("department")

        temp_file = File(file_type=file_type, title="TEMP")
        if file_type == "personal" and owner_id:
            try:
                owner = Staff.objects.get(id=owner_id)
                temp_file.owner = owner
                temp_file.department = owner.department
            except Staff.DoesNotExist:
                pass
        elif file_type == "policy" and department_id:
            try:
                temp_file.department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                pass

        eligible = get_dispatch_recipients(request.user, temp_file)

        if not eligible.exists():
            return HttpResponse(
                '<div class="flex items-center gap-2">'
                '<svg class="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
                '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>'
                "</svg>"
                '<p class="text-sm text-amber-700 font-medium">No recipient found in reporting hierarchy. File will be saved as draft.</p>'
                "</div>"
            )

        recipient = eligible.first()
        full_name = recipient.user.get_full_name() or recipient.user.username
        designation = recipient.designation.name if recipient.designation else "Staff"
        department = recipient.department.name if recipient.department else ""

        return HttpResponse(
            f'<div class="flex items-center gap-3">'
            f'<div class="w-10 h-10 bg-nigeria-light rounded-full flex items-center justify-center">'
            f'<span class="text-nigeria-green font-bold text-sm">{full_name[0]}</span>'
            f"</div>"
            f"<div>"
            f'<p class="text-sm font-bold text-slate-800">{full_name}</p>'
            f'<p class="text-xs text-slate-500">{designation}'
            f'{f" — {department}" if department else ""}</p>'
            f"</div>"
            f"</div>"
        )

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

        for f in self.request.FILES.getlist("attachments"):
            # File creators are always registry: their uploads are official
            # records, so documents start out approved. The file itself stays
            # active (it only leaves active when dispatched for review).
            Document.objects.create(
                file=self.object, attachment=f, uploaded_by=self.request.user, status="approved"
            )

        log_action(self.request.user, "FILE_CREATED", request=self.request, obj=self.object)

        # Notify the relevant party about the new file.
        if self.object.file_type == "personal" and self.object.owner and self.object.owner.user:
            create_notification(
                user=self.object.owner.user,
                message=f"A personnel file has been created for you: {self.object.file_number} — {self.object.title}.",
                obj=self.object,
                link=self.object.get_absolute_url(),
            )
        elif self.object.file_type == "policy" and self.object.department and self.object.department.head and self.object.department.head.user:
            create_notification(
                user=self.object.department.head.user,
                message=f"A policy file has been created in your department: {self.object.file_number} — {self.object.title}.",
                obj=self.object,
                link=self.object.get_absolute_url(),
            )

        save_as_draft = form.cleaned_data.get("save_as_draft", False)
        dispatch_to = form.cleaned_data.get("dispatch_to")

        # Optional dispatch: no selection (or draft ticked) = stay with Registry.
        if save_as_draft or not dispatch_to:
            if save_as_draft:
                messages.success(self.request, "File saved as draft.")
            else:
                messages.success(self.request, "File created and kept with Registry (no dispatch selected).")
            return redirect(self.get_success_url())

        eligible = get_dispatch_recipients(self.request.user, self.object)

        if not eligible.filter(pk=dispatch_to.pk).exists():
            messages.warning(
                self.request,
                "Selected recipient is not eligible. "
                "The file remains with you. You can send it manually from the file detail page.",
            )
            return redirect(self.get_success_url())

        recipient = dispatch_to
        old_location = self.object.current_location
        covering_note = form.cleaned_data.get("covering_note", "")

        self.object.current_location = recipient
        self.object.status = "in_transit"
        self.object.save()

        FileMovement.objects.create(
            file=self.object,
            sent_by=self.request.user,
            from_location=old_location,
            sent_to=recipient,
            note=covering_note,
            action="sent",
        )

        log_action(
            self.request.user,
            "FILE_SENT",
            request=self.request,
            obj=self.object,
            details={"to": recipient.user.get_full_name()},
        )

        create_notification(
            user=recipient.user,
            message=f"{self.request.user.get_full_name()} sent you file {self.object.file_number} — {self.object.title}.",
            obj=self.object,
            link=self.object.get_absolute_url(),
        )

        messages.success(self.request, f"File created and dispatched to {recipient.user.get_full_name()}.")
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

        base_q = Q(owner=staff_user) | Q(created_by=self.request.user) | Q(current_location=staff_user)

        # Heads (HOD / supervisor / unit head) only browse their OWN files on
        # My Files — subordinate personnel files are never listed here. Only
        # the executive tier stays org-wide.
        user = self.request.user
        if user.is_superuser or staff_user.is_executive or staff_user.is_md or getattr(staff_user, "is_mayor", False):
            # org-wide: drop the filter entirely
            queryset = File.objects.all()
        else:
            queryset = File.objects.filter(base_q).distinct()
            is_oversight = (
                staff_user.is_privileged_head or staff_user.is_hod or staff_user.is_head_of_unit
            )
            if not staff_user.is_registry and not is_oversight:
                # Lower staff: My Files shows ONLY pending work still awaiting
                # approval — files in transit OR files with pending/in-transit
                # documents. Once everything is approved (file back to active
                # with no pending docs), it leaves this list. Registry and
                # oversight heads keep their full own-file list.
                queryset = queryset.filter(
                    Q(status="in_transit")
                    | Q(documents__status__in=["pending", "in_transit"])
                ).distinct()

        if not staff_user.is_registry:
            queryset = queryset.exclude(status__in=["inactive", "closed"])

        search_query = self.request.GET.get("q")
        # Lower staff see pending documents only — approved items drop off.
        # Unit managers browsing their unit see full document lists.
        is_lower_staff = not (
            user.is_superuser
            or staff_user.is_registry
            or staff_user.is_hod
            or staff_user.is_privileged_head
            or staff_user.is_head_of_unit
            or staff_user.is_executive
            or staff_user.is_md
            or getattr(staff_user, "is_mayor", False)
        )
        pending_statuses = ["pending", "in_transit"]
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(file_number__icontains=search_query)
                | Q(documents__title__icontains=search_query)
            ).distinct()

            doc_qs = Document.objects.filter(title__icontains=search_query)
            if is_lower_staff:
                doc_qs = doc_qs.filter(status__in=pending_statuses)
            queryset = queryset.prefetch_related(
                Prefetch(
                    "documents",
                    queryset=doc_qs.order_by("-uploaded_at"),
                )
            )
        else:
            doc_qs = Document.objects.all()
            if is_lower_staff:
                doc_qs = doc_qs.filter(status__in=pending_statuses)
            queryset = queryset.prefetch_related(
                Prefetch("documents", queryset=doc_qs.order_by("-uploaded_at"))
            )

        return queryset.select_related(
            "owner__user", "current_location__user", "department"
        ).order_by("-created_at")

    def get_context_data(self, **kwargs):
        staff_user = self.get_staff_user()
        if not staff_user:
            raise Http404("Staff user not found or doesn't exist.")
        context = super().get_context_data(**kwargs)

        personal_folder = File.objects.filter(owner=staff_user, file_type="personal").first()
        context["staff_file_number"] = personal_folder.file_number if personal_folder else "NOT ASSIGNED"
        context["personal_file"] = personal_folder

        context["selected_search_query"] = self.request.GET.get("q", "")
        # Lower staff (including pure heads-of-unit) must never see contents
        # of their OWN personal file. Oversight heads / supervisors /
        # executives / MD / Mayor / registry / superuser keep access.
        user = self.request.user
        context["can_view_own_docs"] = bool(
            user.is_superuser
            or staff_user.is_registry
            or staff_user.is_hod
            or staff_user.is_privileged_head
            or staff_user.is_executive
            or staff_user.is_md
            or getattr(staff_user, "is_mayor", False)
        )
        # Oversight heads get a head-appropriate empty state instead of the
        # regular "caught up / no records" copy.
        context["is_oversight_head"] = bool(
            not staff_user.is_registry
            and (staff_user.is_hod or staff_user.is_privileged_head or staff_user.is_head_of_unit)
        )
        # Jurisdiction browsing: oversight heads plus unit managers (own unit
        # only) get clickable View/Download links on rows in their lists.
        context["can_browse_subordinates"] = bool(
            staff_user.is_hod
            or staff_user.is_privileged_head
            or staff_user.is_head_of_unit
        )
        # Staff-document metadata gate (titles/lists). Registry lacks the
        # view_staff_documents permission, so registry sees file custody info
        # only — never what documents a staff member has.
        from ..permissions import can_view_staff_documents

        context["can_view_staff_docs"] = can_view_staff_documents(user)
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


class FileRecallView(HTMXLoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = "document_management.view_file"

    def post(self, request, pk):
        file_obj = get_object_or_404(File, pk=pk)
        staff_user = self.get_staff_user()

        if file_obj.owner != staff_user and not staff_user.is_registry:
            messages.error(request, "Only the file owner or registry staff can recall a file.")
            return redirect(file_obj.get_absolute_url())

        if file_obj.current_location == staff_user:
            messages.info(request, "File is already with you.")
            return redirect(file_obj.get_absolute_url())

        # Still travelling: the recipient has not acknowledged receipt, so
        # there is nothing settled to pull back yet.
        if file_obj.status == "in_transit":
            messages.error(
                request,
                f"File {file_obj.file_number} is still in transit — it can only be recalled once receipt is acknowledged.",
            )
            return redirect(file_obj.get_absolute_url())

        old_location = file_obj.current_location
        # Recall must never leave custody empty (Unknown Location).
        # Registry recall -> back to recalling registry staff.
        # Owner recall -> back to owner. Fallback -> any registry staff.
        recall_target = None
        if staff_user and staff_user.is_registry:
            recall_target = staff_user
        elif file_obj.owner and staff_user and file_obj.owner == staff_user:
            recall_target = staff_user
        else:
            from organization.models import Staff as StaffModel

            from django.db.models import Q

            recall_target = StaffModel.objects.filter(
                Q(designation__name__icontains="registry") | Q(user__groups__name__iexact="Registry")
            ).first()
        if recall_target is None:
            messages.error(request, "No Registry custodian found. Recall aborted — custody would be empty.")
            return redirect(file_obj.get_absolute_url())
        file_obj.current_location = recall_target
        file_obj.status = "active"
        file_obj.save()

        FileMovement.objects.create(
            file=file_obj,
            sent_by=request.user,
            from_location=old_location,
            sent_to=recall_target,
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

        if staff_user.is_md or getattr(staff_user, "is_mayor", False) or staff_user.is_executive:
            return True  # MD / Mayor / Executive see all files org-wide

        if file_obj.file_type == "policy":
            if staff_user.is_hod and file_obj.department == staff_user.department:
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

        # Section / division heads + supervisors see personal files of staff
        # in their jurisdiction (same section / division, falling back to
        # same department).
        # Section / division heads + supervisors see personal files of staff
        # in their jurisdiction (same section / division, falling back to
        # same department).
        # Heads of unit see personal files of staff in their OWN unit only.
        if file_obj.file_type == "personal" and file_obj.owner:
            owner = file_obj.owner
            if staff_user.is_privileged_head:
                try:
                    headed_section = staff_user.headed_section
                except Exception:
                    headed_section = None
                if headed_section and owner.section_id and owner.section_id == headed_section.pk:
                    return True
                try:
                    headed_division = staff_user.headed_division
                except Exception:
                    headed_division = None
                if headed_division and owner.division_id and owner.division_id == headed_division.pk:
                    return True
                if (
                    owner.department_id
                    and staff_user.department_id
                    and owner.department_id == staff_user.department_id
                ):
                    return True
            if owner.pk != staff_user.pk and staff_user.is_head_of_unit:
                try:
                    headed_unit = staff_user.headed_unit
                except Exception:
                    headed_unit = None
                if headed_unit is not None and owner.unit_id and owner.unit_id == headed_unit.pk:
                    return True

        if file_obj.owner == staff_user:
            # Owner can see the file page but needs an access request to view content
            return True

        if file_obj.current_location == staff_user:
            return True

        # Dispatch members: anyone sent this file via a FileMovement retains
        # the ability to view the (limited) file page. This lets a dispatched
        # recipient request (re-)access once their movement has expired, instead
        # of being hard-redirected away. Actual contents access is still gated in
        # get_context_data via is_approved_access / movement.is_active_access.
        if file_obj.movements.filter(sent_to=staff_user, action="sent").exists():
            return True

        has_approved_access = (
            FileAccessRequest.objects.filter(file=file_obj, requested_by=user, status="approved")
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )

        return bool(has_approved_access)

    def _reclaim_expired_custody(self, file_obj):
        """If current custodian holds the file via an expired movement or access request, return it to registry."""
        holder = file_obj.current_location
        if not holder or holder.is_registry:
            return
        # Check if holder is the file owner — owners always keep custody
        if file_obj.owner == holder:
            return
        # Active via an approved, unexpired FileAccessRequest
        has_active_request = (
            FileAccessRequest.objects.filter(file=file_obj, requested_by=holder.user, status="approved")
            .filter(Q(expires_at__gt=timezone.now()) | Q(expires_at__isnull=True))
            .exists()
        )
        # Active via a movement dispatched to this holder (the new source of truth)
        latest_movement = file_obj.movements.filter(
            sent_to=holder, action="sent"
        ).order_by("-moved_at").first()
        has_active_movement = bool(latest_movement and latest_movement.is_active_access)
        if not (has_active_request or has_active_movement):
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
        Standing access: owner, uploader, Executive/MD/Mayor. HODs, unit
        heads, and supervisors need custody or an explicit grant (approved
        request, active movement, share). Registry staff can never view
        contents (separation-of-duties).
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
        is_owner = hasattr(user, "staff") and file_obj.owner == user.staff

        # Owners can view contents of their own file (role scope in
        # can_view_document_content) — restriction below only applies when
        # the viewer genuinely cannot view. Functional access
        # (adding/managing documents) still follows custody and grants below,
        # so an owner can file new records regardless.
        staff = getattr(user, "staff", None)
        is_privileged_viewer = bool(
            user.is_superuser
            or (staff and (staff.is_registry or staff.is_hod or staff.is_privileged_head
                           or staff.is_executive or staff.is_md or getattr(staff, "is_mayor", False)))
        )
        is_own_personal_file = bool(
            staff and file_obj.file_type == "personal" and file_obj.owner_id and file_obj.owner_id == staff.pk
        )
        is_own_restricted = bool(is_own_personal_file and not self.can_view_original(file_obj, user))
        context["is_own_restricted"] = is_own_restricted
        # Custodian always carries access. Owner carries automatic access
        # ONLY while holding custody — when file is at rest with Registry
        # (or in transit with someone else) the owner must request access
        # like anyone else instead of silently keeping Full Access.
        if is_custodian or (is_owner and is_custodian):
            has_approved_access = True
            has_rw_access = True
        else:
            # Movement-based access: a recipient dispatched via "Send Note" is granted
            # automatic access that is tracked by FileMovement (with optional expiry).
            staff = getattr(user, "staff", None)
            latest_movement = None
            if staff:
                latest_movement = (
                    file_obj.movements.filter(sent_to=staff, action="sent").order_by("-moved_at").first()
                )
            if latest_movement and latest_movement.is_active_access:
                has_approved_access = True
                has_rw_access = True
            else:
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
        is_mayor = bool(hasattr(user, "staff") and getattr(user.staff, "is_mayor", False))

        # Registry staff (and superusers) have full administrative access to every
        # file, so they always carry approved read & write access.
        # Mayor carries Read & Write on every file as well.
        if is_registry or user.is_superuser or is_mayor:
            has_approved_access = True
            has_rw_access = True

        # Same rule set as the endpoint (DocumentCreateView.dispatch), so the
        # button is only shown when adding will actually be allowed.
        context["can_add_minute"] = can_add_document(user, file_obj)
        context["can_add_minutes"] = context["can_add_minute"]
        from document_management.permissions import can_manual_dispatch

        context["can_send_file"] = (
            (is_custodian or is_registry or is_mayor)
            and file_obj.status == "active"
            and can_manual_dispatch(user)
        )
        # Custody-derived gating: at rest with Registry vs in transit with third party.
        # At rest (active + holder is Registry)  -> request access FROM Registry.
        # In transit (status in_transit, or holder is neither owner nor Registry)
        #   -> requests blocked until receipt is acknowledged.
        holder = file_obj.current_location
        holder_is_registry = bool(holder and holder.is_registry)
        is_at_rest_with_registry = bool(holder_is_registry and file_obj.status == "active")
        is_in_transit = file_obj.status == "in_transit"
        custodian_is_third_party = bool(holder and file_obj.owner and holder != file_obj.owner and not holder_is_registry)
        pending_access_request = FileAccessRequest.objects.filter(
            file=file_obj, requested_by=user, status="pending"
        ).exists()
        # Access levels are role-restricted: normal staff may only request
        # Read & Write, while Read-Only is reserved for supervisor roles.
        is_supervisor_viewer = bool(staff and staff.is_effective_supervisor)
        can_request_ro = bool(
            is_supervisor_viewer and user.has_perm("user_management.can_request_file_access")
        )
        can_request_rw = user.has_perm("user_management.can_request_file_access_rw")
        can_request_access = bool(
            not has_approved_access
            and not pending_access_request
            and not is_registry
            and file_obj.status == "active"
            and is_at_rest_with_registry
            and (can_request_ro or can_request_rw)
        )
        context["is_custodian"] = is_custodian
        context["is_owner"] = is_owner
        context["has_approved_access"] = has_approved_access
        context["has_rw_access"] = has_rw_access
        context["access_type"] = "read_write" if has_rw_access else ("read_only" if has_approved_access else None)
        context["can_request_ro_access"] = can_request_ro
        context["can_request_rw_access"] = can_request_rw
        context["is_registry"] = is_registry
        context["can_view_original"] = self.can_view_original(file_obj, user)
        context["is_limited_view"] = not context["can_view_original"]
        context["is_at_rest_with_registry"] = is_at_rest_with_registry
        context["is_in_transit"] = is_in_transit
        context["custodian_is_third_party"] = custodian_is_third_party
        context["can_request_access"] = can_request_access
        # Transit block takes precedence over any stale approved grant:
        # viewer is neither custodian nor registry/superuser while the file
        # sits with someone else -> show "in transit, cannot request" instead of Full.
        context["show_transit_block"] = bool(
            (is_in_transit or custodian_is_third_party)
            and not is_custodian
            and not is_registry
            and not user.is_superuser
        )
        sender_staff = getattr(user, "staff", None)
        context["send_file_form"] = SendFileForm(user=user, staff=sender_staff, file_obj=file_obj)
        context["access_request_form"] = FileAccessRequestForm()
        context["pending_access_request"] = pending_access_request
        context["movements"] = file_obj.movements.select_related("sent_by", "from_location__user", "sent_to__user")[:20]

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

        # Build unified chronicle
        documents = list(file_obj.documents.select_related("uploaded_by").all())
        context["documents"] = documents
        # Approved documents are locked per-document: titles/status stay
        # visible, but contents + buttons hide unless the viewer is top
        # leadership, holds custody, holds a file-level approved grant, or
        # is shared directly on that document.
        _can_open_approved = bool(
            user.is_superuser
            or is_custodian
            or has_approved_access
            or (
                staff
                and (
                    staff.is_executive or staff.is_md or getattr(staff, "is_mayor", False)
                )
            )
        )
        _shared_ids = set()
        if not _can_open_approved and staff:
            _shared_ids = set(
                file_obj.documents.filter(shared_with=user, status="approved").values_list(
                    "pk", flat=True
                )
            )
        context["locked_doc_ids"] = {
            doc.pk
            for doc in documents
            if doc.status == "approved" and not _can_open_approved and doc.pk not in _shared_ids
        }
        audit_entries = list(
            AuditLogEntry.objects.filter(object_id=file_obj.pk, content_type__model="file")
            .select_related("user")
            .order_by("timestamp")
        )

        chronicle = []
        for doc in documents:
            chronicle.append({"type": "document", "item": doc, "timestamp": doc.uploaded_at})
        for entry in audit_entries:
            chronicle.append({"type": "audit", "item": entry, "timestamp": entry.timestamp})
        chronicle.sort(key=lambda x: x["timestamp"])
        context["chronicle"] = chronicle

        return context

    def post(self, request, *args, **kwargs):
        file_obj = self.get_object()
        action = request.POST.get("action")

        if action == "change_status":
            staff_user = getattr(request.user, "staff", None)
            is_registry = bool(
                request.user.is_superuser or (staff_user and staff_user.is_registry)
            )
            if not is_registry:
                messages.error(request, "Only Registry can change a file's status.")
                return redirect(file_obj.get_absolute_url())
            new_status = (request.POST.get("new_status") or "").strip()
            if new_status not in ("active", "inactive"):
                messages.error(request, "Only Active or Inactive can be selected.")
                return redirect(file_obj.get_absolute_url())
            if file_obj.status not in ("active", "inactive"):
                messages.error(
                    request,
                    f"Status cannot be changed while the file is '{file_obj.get_status_display()}'.",
                )
                return redirect(file_obj.get_absolute_url())
            if new_status == file_obj.status:
                messages.info(request, f"File is already '{file_obj.get_status_display()}'.")
                return redirect(file_obj.get_absolute_url())
            old_display = file_obj.get_status_display()
            file_obj.status = new_status
            file_obj.save(update_fields=["status"])
            log_action(
                request.user,
                "FILE_STATUS_CHANGED",
                request=request,
                obj=file_obj,
                details={"from": old_display, "to": file_obj.get_status_display()},
            )
            messages.success(
                request, f"File status changed from {old_display} to {file_obj.get_status_display()}."
            )
            return redirect(file_obj.get_absolute_url())

        if action == "request_access":
            already_pending = FileAccessRequest.objects.filter(
                file=file_obj, requested_by=request.user, status="pending"
            ).exists()
            holder = file_obj.current_location
            holder_is_registry = bool(holder and holder.is_registry)
            requester_staff = getattr(request.user, "staff", None)
            requester_is_supervisor = bool(
                requester_staff and requester_staff.is_effective_supervisor
            )
            access_type = (request.POST.get("access_type") or "").strip().lower()
            if access_type not in ("read_only", "read_write"):
                # Anything unexpected falls back to the level the requester is
                # actually entitled to (staff -> Read & Write only).
                access_type = "read_write" if not requester_is_supervisor else "read_only"
            if already_pending:
                messages.warning(request, "You already have a pending access request for this file.")
            elif file_obj.status == "in_transit" or (holder and file_obj.owner and holder != file_obj.owner and not holder_is_registry):
                messages.error(request, "File is in transit with another custodian. Wait until it returns to Registry before requesting access.")
            elif not (holder_is_registry and file_obj.status == "active"):
                messages.error(request, "Access can only be requested when the file is at rest with Registry.")
            elif access_type == "read_write" and not request.user.has_perm("user_management.can_request_file_access_rw"):
                messages.error(request, "You do not have permission to request Read & Write access.")
            elif access_type == "read_only" and not (
                requester_is_supervisor
                and request.user.has_perm("user_management.can_request_file_access")
            ):
                messages.error(request, "Read-Only access requests are reserved for supervisors.")
            else:
                FileAccessRequest.objects.create(
                    file=file_obj,
                    requested_by=request.user,
                    access_type=access_type,
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

            from document_management.permissions import can_manual_dispatch as _can_dispatch

            if not _can_dispatch(request.user):
                messages.error(
                    request,
                    "Only Registry, HODs, supervisors, and executives can dispatch files. "
                    "Your documents route automatically to your head.",
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
                    expires_at=timezone.now() + timedelta(days=7),
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

        return redirect("document_management:staff_folder_list")

    def handle_no_permission(self):
        messages.error(self.request, "You do not have permission to archive files.")
        return redirect("document_management:staff_folder_list")


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
        context["pending_access_count"] = FileAccessRequest.objects.filter(status="pending").count()
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
        return redirect("document_management:staff_folder_list")


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
        # Unit managers see only their unit's personal files, excluding their own
        # MD sees everything
        if staff and staff.is_hod and not staff.is_md and not staff.is_registry and not self.request.user.is_superuser:
            dept = staff.department
            queryset = (
                queryset.filter(Q(department=dept) | Q(file_type="personal", owner__department=dept))
                .exclude(file_type="personal", owner=staff)
                .distinct()
            )
        elif (
            staff
            and staff.is_head_of_unit
            and not staff.is_hod
            and not staff.is_md
            and not staff.is_registry
            and not self.request.user.is_superuser
        ):
            try:
                headed_unit = staff.headed_unit
            except Exception:
                headed_unit = None
            if headed_unit:
                queryset = (
                    queryset.filter(Q(file_type="personal", owner__unit=headed_unit))
                    .exclude(file_type="personal", owner=staff)
                    .distinct()
                )
            else:
                queryset = queryset.none()

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
    if staff.is_md or staff.is_executive or getattr(staff, "is_mayor", False):
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
    """Unified inbox: file movements AND urgent/high-priority documents in one list.

    Rows come from two sources merged, newest first:
      * FileMovements sent to this staff member (the classic inbox).
      * Urgent/high priority documents from accessible active files plus
        standalone urgent documents (the old "urgent" mode).

    Tabs (?tab=):
      untreated (default) — pending movements + pending/in-transit urgent docs.
      treated             — approved/rejected/forwarded movements + closed docs.

    Filter (?filter=):
      all     — everything (default).
      urgent  — only urgent/high priority rows (?mode=urgent is an alias).
    """

    model = FileMovement
    template_name = "document_management/inbox.html"
    context_object_name = "movements"
    paginate_by = 15

    TREATED_STATUSES = ["approved", "rejected", "forwarded"]
    UNTREATED_DOC_STATUSES = ["pending", "in_transit"]
    TREATED_DOC_STATUSES = ["approved", "rejected", "cancelled"]
    ROW_LIMIT = 1000  # safety cap per source when merging in Python

    # ------------------------------------------------------------------ params
    def get_current_tab(self):
        tab = self.request.GET.get("tab", "untreated")
        return tab if tab in ("untreated", "treated") else "untreated"

    def get_current_filter(self):
        """'all' or 'urgent'. ?mode=urgent still works (old links)."""
        f = self.request.GET.get("filter", "")
        if f in ("all", "urgent"):
            return f
        if self.request.GET.get("mode") == "urgent":
            return "urgent"
        return "all"

    # ------------------------------------------------------------------ sources
    def _user_files(self, staff):
        return File.objects.filter(
            Q(current_location=staff)
            | Q(owner=staff)
            | (Q(department=staff.department) if staff.department else Q()),
            status="active",
        ).distinct()

    def _movement_qs(self, staff):
        return (
            FileMovement.objects.filter(sent_to=staff, action="sent")
            .select_related("file", "document", "sent_by", "from_location__user")
            .order_by("-moved_at")
        )

    def _tab_movements(self, staff, tab):
        qs = self._movement_qs(staff)
        if tab == "treated":
            return qs.filter(status__in=self.TREATED_STATUSES)
        return qs.filter(status="pending")

    def _urgent_doc_qs(self, staff, tab):
        qs = (
            Document.objects.filter(
                Q(file__in=self._user_files(staff)) | Q(file__isnull=True),
                priority__in=["urgent", "high"],
            )
            .select_related("file", "uploaded_by")
            .order_by("-uploaded_at")
        )
        if tab == "treated":
            return qs.filter(status__in=self.TREATED_DOC_STATUSES)
        return qs.filter(status__in=self.UNTREATED_DOC_STATUSES)

    # ------------------------------------------------------------------ rows
    @staticmethod
    def _movement_row(movement):
        priority = movement.document.priority if movement.document else "normal"
        return {
            "kind": "movement",
            "obj": movement,
            "date": movement.moved_at,
            "priority": priority,
            "is_urgent": priority in ("urgent", "high"),
        }

    @staticmethod
    def _document_row(document):
        return {
            "kind": "document",
            "obj": document,
            "date": document.uploaded_at,
            "priority": document.priority,
            "is_urgent": document.priority in ("urgent", "high"),
        }

    def _build_rows(self, staff, tab, urgent_only):
        movements = list(self._tab_movements(staff, tab)[: self.ROW_LIMIT])
        # A document already shown as a movement row must not appear twice.
        seen_doc_ids = [m.document_id for m in movements if m.document_id]
        documents = list(
            self._urgent_doc_qs(staff, tab).exclude(pk__in=seen_doc_ids)[: self.ROW_LIMIT]
        )

        # Standalone urgent documents have no movement — decisions happen on
        # their detail page, never inline in the list.
        rows = [self._movement_row(m) for m in movements]
        rows.extend(self._document_row(d) for d in documents)
        if urgent_only:
            rows = [r for r in rows if r["is_urgent"]]
        rows.sort(key=lambda r: r["date"], reverse=True)
        return rows

    def get_queryset(self):
        staff = getattr(self.request.user, "staff", None)
        if not staff:
            return []
        return self._build_rows(
            staff,
            self.get_current_tab(),
            self.get_current_filter() == "urgent",
        )

    # ------------------------------------------------------------------ context
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = getattr(self.request.user, "staff", None)
        context["current_tab"] = self.get_current_tab()
        context["current_filter"] = self.get_current_filter()
        # Legacy template/links key — 'urgent' while the urgent filter is on.
        context["current_mode"] = "urgent" if context["current_filter"] == "urgent" else "inbox"

        if staff:
            mov_untreated = self._tab_movements(staff, "untreated")
            mov_treated = self._tab_movements(staff, "treated")
            # Urgent docs already represented by a movement row are excluded so
            # the counts match what the merged list actually shows.
            doc_untreated = self._urgent_doc_qs(staff, "untreated").exclude(
                pk__in=mov_untreated.exclude(document__isnull=True).values("document_id")
            )
            doc_treated = self._urgent_doc_qs(staff, "treated").exclude(
                pk__in=mov_treated.exclude(document__isnull=True).values("document_id")
            )
            mov_untreated_urgent = mov_untreated.filter(document__priority__in=["urgent", "high"])
            mov_treated_urgent = mov_treated.filter(document__priority__in=["urgent", "high"])

            context["untreated_count"] = mov_untreated.count() + doc_untreated.count()
            context["treated_count"] = mov_treated.count() + doc_treated.count()
            context["urgent_untreated_count"] = mov_untreated_urgent.count() + doc_untreated.count()
            context["urgent_treated_count"] = mov_treated_urgent.count() + doc_treated.count()
        else:
            for key in (
                "untreated_count",
                "treated_count",
                "urgent_untreated_count",
                "urgent_treated_count",
            ):
                context[key] = 0

        # Counts for the filter chips follow the active tab.
        context["tab_all_count"] = (
            context["treated_count"]
            if context["current_tab"] == "treated"
            else context["untreated_count"]
        )
        context["tab_urgent_count"] = (
            context["urgent_treated_count"]
            if context["current_tab"] == "treated"
            else context["urgent_untreated_count"]
        )

        # Keeps ?tab= / ?filter= across pagination links.
        context["pagination_extra"] = (
            f"&tab={context['current_tab']}&filter={context['current_filter']}"
        )

        # An htmx swap renders only the panel, so flash messages must be drawn
        # there. A full page load already shows them above the block content.
        context["hx_request"] = bool(self.request.headers.get("HX-Request"))

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

        can_view_content = can_view_document_content(request.user, file=doc.file)

        return render(
            request,
            "document_management/inbox_ref_doc.html",
            {
                "document": doc,
                "can_view_content": can_view_content,
            },
        )


class InboxFileView(HTMXLoginRequiredMixin, View):
    """File view for a movement recipient — Mayor carries Read & Write and full content access."""

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
        is_mayor = bool(staff and getattr(staff, "is_mayor", False))
        query = request.GET.get("q", "").strip()
        all_documents = file_obj.documents.select_related("uploaded_by").order_by("-uploaded_at")
        if query:
            all_documents = all_documents.filter(
                Q(title__icontains=query) | Q(minute_content__icontains=query)
            )

        # Reference documents shared with this user for this movement
        reference_docs = (
            file_obj.documents.filter(shared_with=request.user)
            .exclude(pk=movement.document.pk if movement.document else None)
            .order_by("-uploaded_at")
        )

        can_view_content = can_view_document_content(request.user, file=file_obj)
        # Mayor always sees full content with Read & Write.
        if is_mayor:
            can_view_content = True
        # Current custodian (movement recipient holding the file) carries RW.
        is_holder = bool(staff and file_obj.current_location == staff)
        is_recipient = bool(staff and movement.sent_to == staff)
        has_rw = bool(
            staff
            and (is_holder or is_mayor or (is_recipient and movement.is_active_access))
            and file_obj.status in ("active", "in_transit")
        )

        return render(
            request,
            "document_management/inbox_file_view.html",
            {
                "movement": movement,
                "file": file_obj,
                "all_documents": all_documents,
                "reference_docs": reference_docs,
                "can_view_content": can_view_content,
                "search_query": query,
                "is_holder": is_holder,
                "is_recipient": is_recipient,
                "has_rw": has_rw,
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

        can_view_content = can_view_document_content(request.user, file=file_obj)

        from document_management.views.document_views import can_download_document_file

        can_download_file = bool(
            document is not None and can_download_document_file(request.user, document)
        )

        # Per-document buttons: only show View/Download where the gate passes,
        # so unauthorized viewers never even see the buttons.
        viewable_doc_ids = set()
        downloadable_doc_ids = set()
        for _d in list(other_docs) + list(reference_docs):
            try:
                if can_view_document_content(request.user, file=file_obj, document=_d):
                    viewable_doc_ids.add(_d.pk)
                if can_download_document_file(request.user, _d):
                    downloadable_doc_ids.add(_d.pk)
            except Exception:
                continue

        is_top_approver = bool(
            staff
            and (
                staff.is_hod or staff.is_md or staff.is_executive or getattr(staff, "is_mayor", False)
            )
        )
        is_hou_forwarder = bool(staff and staff.is_unit_manager and not is_top_approver)
        is_final_approver = bool(staff and staff.can_final_approve)

        # Prefill the approver search for anyone who cannot settle the
        # document themselves (everyone but the Medical Director role).
        prefilled_recipient = None
        if staff is not None and not is_final_approver:
            from document_management.permissions import get_final_approvers

            prefilled_recipient = get_final_approvers(exclude_staff=staff).first()

        # Next hop after this movement — forwards create a follow-up
        # movement that carries the decision note + timestamp.
        next_movement = None
        if movement.status == "forwarded" and document is not None:
            next_movement = (
                FileMovement.objects.filter(document=document, moved_at__gt=movement.moved_at)
                .select_related("sent_by", "sent_to__user")
                .order_by("moved_at")
                .first()
            )

        # Decision audit record — reject reasons and decision timestamps
        # live only in the audit trail (the movement row itself is not
        # stamped when actioned).
        decision_entry = None
        if movement.status in ("approved", "rejected"):
            from django.contrib.contenttypes.models import ContentType

            action = "DOCUMENT_APPROVED" if movement.status == "approved" else "DOCUMENT_REJECTED"
            actor_user = movement.sent_to.user if movement.sent_to and movement.sent_to.user_id else None
            entry_qs = AuditLogEntry.objects.filter(
                action=action,
                content_type=ContentType.objects.get_for_model(file_obj),
                object_id=file_obj.pk,
            ).order_by("-timestamp")
            if actor_user is not None:
                entry_qs = entry_qs.filter(user=actor_user)
            decision_entry = entry_qs.first()

        # Whether the viewer may open the next hop in the trail.
        can_follow_trail = bool(
            next_movement
            and (
                next_movement.sent_by_id == request.user.pk
                or (staff is not None and next_movement.sent_to_id == staff.pk)
            )
        )

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
                "can_download_file": can_download_file,
                "viewable_doc_ids": viewable_doc_ids,
                "downloadable_doc_ids": downloadable_doc_ids,
                "can_approve": bool(
                    staff
                    and (
                        is_final_approver
                        or staff.is_hod
                        or staff.is_effective_supervisor
                        or staff.is_unit_manager
                    )
                ),
                "is_final_approver": is_final_approver,
                "is_hou_forwarder": is_hou_forwarder,
                "prefilled_recipient": prefilled_recipient,
                "next_movement": next_movement,
                "decision_entry": decision_entry,
                "can_follow_trail": can_follow_trail,
            },
        )


def _expire_actioned_movement_access(movement, actor):
    """Revoke dispatch-time access once a movement is approved/forwarded/rejected.

    - The actioned movement itself is expired, so it no longer grants viewing
      or downloading (its ``is_active_access`` goes False).
    - Dispatch-time auto-grants (``Auto-granted: ...`` FileAccessRequests
      minted for sender/recipient at send time) are revoked: all of them on
      terminal actions (approve/reject), only the actor's on forward since
      the next recipient rides on their fresh movement + custody.
    - Real, human-approved access requests are NEVER touched — requesting
      access stays the legitimate way back in for staff, HOUs, HODs, and
      supervisors alike.
    """
    movement.expires_at = timezone.now()
    movement.save(update_fields=["expires_at"])
    auto_grants = FileAccessRequest.objects.filter(
        file=movement.file, status="approved", reason__startswith="Auto-granted"
    )
    if movement.status == "forwarded":
        auto_grants = auto_grants.filter(requested_by=actor)
    auto_grants.update(status="expired")


class DocumentActionView(HTMXLoginRequiredMixin, View):
    """Approve / forward / reject a document received via FileMovement.

    - Approver (holder of ``can_approve_document`` — the Medical Director
      role): Approve is final — the document is approved and custody goes
      back to Registry.
    - HOD / HOU / supervisor WITHOUT that permission: Approve records their
      approval on the movement and routes the document to an approver picked
      from the approver search, so the history shows their approval while
      the document itself stays pending. Reject (note required) returns it
      to the sender; supervisors may still Forward explicitly.
    - Acting closes the loop: the actioned movement stops granting access
      and dispatch-time auto-grants are revoked (see
      _expire_actioned_movement_access), so nobody can go back to the
      inbox/sent item to keep viewing or downloading. Requesting access
      remains the way back in.
    """

    def _respond(self, request):
        """htmx gets a freshly rendered inbox panel; plain posts redirect."""
        return inbox_action_response(request, "document_management:inbox")

    def post(self, request, pk):
        movement = get_object_or_404(FileMovement, pk=pk)
        staff = getattr(request.user, "staff", None)

        if movement.sent_to != staff:
            messages.error(request, "This document was not sent to you.")
            return self._respond(request)

        if movement.status != "pending":
            messages.error(request, "This document has already been actioned.")
            return self._respond(request)

        # Prevent the document creator from approving/rejecting their own document
        if movement.document and movement.document.uploaded_by == request.user:
            messages.error(request, "You cannot approve or reject your own document.")
            return self._respond(request)

        action = request.POST.get("action")
        note = request.POST.get("note", "").strip()

        # Two approval modes. The holder of ``can_approve_document`` (the
        # Medical Director role) settles the document. Everyone else who may
        # decide — HOD, HOU, supervisor — records their approval and routes
        # the document to an approver picked from the search, so their
        # approval shows in the history while the document stays pending.
        is_final_approver = bool(staff and staff.can_final_approve)
        is_top_approver = bool(
            staff
            and (
                staff.is_hod
                or staff.is_md
                or staff.is_executive
                or getattr(staff, "is_mayor", False)
            )
        )
        is_hou_forwarder = bool(staff and staff.is_unit_manager and not is_top_approver)
        may_decide = bool(
            staff
            and (is_final_approver or is_top_approver or is_hou_forwarder or staff.is_effective_supervisor)
        )

        if action == "approve":
            if not may_decide:
                messages.error(request, "Only HODs, supervisors, unit managers, and staff with approval rights can act on documents.")
                return self._respond(request)

            if is_final_approver:
                # Approver (Medical Director): final approval
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
                        "approver_role": staff.role_label,
                        "final": True,
                    },
                )
                messages.success(request, "Document approved.")

            else:
                # No approval right: the approval is recorded on this
                # movement and the document goes to an approver for the
                # final decision. Document status stays pending.
                from django.db.models import Q as DQ
                from organization.models import Staff as StaffModel

                recipient_staff_id = (
                    request.POST.get("recipient_staff_id") or request.POST.get("recipient") or ""
                ).strip()
                if not recipient_staff_id:
                    messages.error(request, "Select an approver to give final approval.")
                    return self._respond(request)

                recipient = (
                    StaffModel.objects.select_related("user", "designation", "department", "unit")
                    .filter(pk=recipient_staff_id)
                    .first()
                )
                if recipient is None or recipient.pk == staff.pk:
                    messages.error(request, "Select a valid approver.")
                    return self._respond(request)
                if not recipient.can_final_approve:
                    messages.error(request, "Selected staff cannot give final approval.")
                    return self._respond(request)

                # Optional reference documents from the same file to share
                # with the approver for context.
                ref_ids = request.POST.getlist("reference_documents")
                ref_docs = []
                if ref_ids:
                    ref_docs = list(
                        movement.file.documents.exclude(
                            pk=movement.document.pk if movement.document else None
                        ).filter(pk__in=ref_ids)
                    )
                    for ref_doc in ref_docs:
                        ref_doc.shared_with.add(recipient.user)

                movement.status = "approved"
                movement.save(update_fields=["status"])
                new_movement = FileMovement.objects.create(
                    file=movement.file,
                    document=movement.document,
                    sent_by=request.user,
                    from_location=staff,
                    sent_to=recipient,
                    note=note,
                    action="sent",
                )
                # The approver rides on the fresh movement + custody.
                movement.file.current_location = recipient
                movement.file.save(update_fields=["current_location"])
                sender_name = request.user.get_full_name() or request.user.username
                doc_ref = movement.document or movement.file.file_number
                suffix = f" (+{len(ref_docs)} reference doc(s))" if ref_docs else ""
                create_notification(
                    user=recipient.user,
                    message=(
                        f"{sender_name} approved document '{doc_ref}' and sent it to you "
                        f"for final approval{suffix}."
                    ),
                    obj=movement.file,
                    link=reverse_lazy("document_management:inbox"),
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
                        "approver_role": staff.role_label,
                        "final": False,
                        "to": recipient.user.get_full_name(),
                        "to_staff_id": recipient.pk,
                        "reference_doc_ids": [d.pk for d in ref_docs],
                        "approval_movement_id": new_movement.pk,
                    },
                )
                messages.success(
                    request,
                    f"Approved — sent to {recipient.user.get_full_name()} for final approval.",
                )

        elif action == "forward":
            # Explicit forward for supervisors / HODs to another
            # supervisor/HOD with optional reference docs + note.
            # Unit managers route their approval to an approver instead.
            if is_hou_forwarder:
                messages.error(request, "Unit managers route approvals to an approver.")
                return self._respond(request)
            if not staff or not (
                is_top_approver or staff.is_effective_supervisor
            ):
                messages.error(request, "Only HODs and supervisors can forward documents.")
                return self._respond(request)

            recipient_staff_id = (
                request.POST.get("recipient_staff_id") or request.POST.get("recipient") or ""
            ).strip()
            if not recipient_staff_id:
                messages.error(request, "Select a supervisor or HOD to forward to.")
                return self._respond(request)

            recipient = None
            try:
                eligible = get_dispatch_recipients(request.user, movement.file)
                recipient = eligible.filter(pk=recipient_staff_id).first()
            except Exception:
                recipient = None
            if recipient is None:
                messages.error(request, "Selected recipient is not eligible for forwarding.")
                return self._respond(request)

            ref_ids = request.POST.getlist("reference_documents")
            ref_docs = []
            if ref_ids:
                ref_docs = list(
                    movement.file.documents.exclude(
                        pk=movement.document.pk if movement.document else None
                    ).filter(pk__in=ref_ids)
                )
                for ref_doc in ref_docs:
                    ref_doc.shared_with.add(recipient.user)

            movement.status = "forwarded"
            movement.save(update_fields=["status"])
            new_movement = FileMovement.objects.create(
                file=movement.file,
                document=movement.document,
                sent_by=request.user,
                from_location=staff,
                sent_to=recipient,
                note=note,
                action="sent",
            )
            movement.file.current_location = recipient
            movement.file.save(update_fields=["current_location"])
            sender_name = request.user.get_full_name() or request.user.username
            doc_ref = movement.document or movement.file.file_number
            suffix = f" (+{len(ref_docs)} reference doc(s))" if ref_docs else ""
            create_notification(
                user=recipient.user,
                message=f"{sender_name} forwarded document '{doc_ref}' to you{suffix}.",
                obj=movement.file,
                link=reverse_lazy("document_management:inbox"),
            )
            log_action(
                request.user,
                "DOCUMENT_FORWARDED",
                request=request,
                obj=movement.file,
                details={
                    "document": str(movement.document),
                    "file": movement.file.file_number,
                    "to": recipient.user.get_full_name(),
                    "to_staff_id": recipient.pk,
                    "note": note,
                    "reference_doc_ids": [d.pk for d in ref_docs],
                    "forward_movement_id": new_movement.pk,
                },
            )
            messages.success(request, f"Document forwarded ({recipient.user.get_full_name()}).")

        elif action == "reject":
            if not staff or not (
                is_final_approver
                or staff.is_hod
                or staff.is_effective_supervisor
                or staff.is_unit_manager
            ):
                messages.error(request, "Only HODs, supervisors, unit managers, and staff with approval rights can reject documents.")
                return self._respond(request)

            if not note:
                messages.error(request, "A reason is required when rejecting a document.")
                return self._respond(request)

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
                    "rejector_role": staff.role_label,
                },
            )
            messages.warning(request, "Document rejected and returned to sender.")

        else:
            messages.error(request, "Invalid action.")

        # The movement was actioned (status left "pending" above) — close the
        # access loop so the inbox/sent item can't be revisited for viewing
        # or downloading.
        if movement.status in ("approved", "forwarded", "rejected"):
            _expire_actioned_movement_access(movement, actor=request.user)

        return self._respond(request)


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
        return redirect("document_management:staff_folder_list")

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
        return redirect("document_management:staff_folder_list")

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
            messages.error(request, "You need an active digital signature to approve this file.")
            return redirect(file_obj.get_absolute_url())
        
        action = request.POST.get("action")
        
        if action == "approve":
            # Approve the file - files go straight to active.
            file_obj.status = "active"
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
                        message=f"File {file_obj.file_number} — {file_obj.title} has been approved by {staff.user.get_full_name()} and is now active.",
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
                    message=f"File {file_obj.file_number} — {file_obj.title} has been approved and is now active.",
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
            
            messages.success(request, "File creation approved successfully. File is now active.")
            
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
            messages.error(request, "You need an active digital signature to approve this document.")
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
