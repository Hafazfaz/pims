from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.views.generic import View
from organization.models import Staff, Unit

from .base import EXCLUDE_REGISTRY_Q


def _reporting_hierarchy_pks(sender_staff):
    """Heads above the sender, skipping self (a unit manager's direct head
    is THEIR head, not themselves)."""
    for head in (
        sender_staff.unit.head if sender_staff.unit else None,
        sender_staff.section.head if sender_staff.section else None,
        sender_staff.division.head if sender_staff.division else None,
        sender_staff.department.head if sender_staff.department else None,
    ):
        if head and head.pk != sender_staff.pk:
            return [head.pk]
    return []


class RecipientSearchView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        from document_management.permissions import can_manual_dispatch

        if not can_manual_dispatch(request.user):
            return HttpResponse(
                '<div class="px-4 py-3 text-xs text-slate-500 italic text-center">Dispatch is restricted to Registry, HODs, supervisors, and executives.</div>'
            )

        query = request.GET.get("q", "").strip()
        if not query or len(query) < 2:
            return HttpResponse("")

        sender_staff = getattr(request.user, "staff", None)
        base_qs = (
            Staff.objects.exclude(EXCLUDE_REGISTRY_Q)
            .exclude(user=request.user)
            .select_related("user", "designation", "department", "unit", "headed_unit", "headed_department")
        )

        if sender_staff:
            if sender_staff.is_md or sender_staff.is_executive:
                eligible_qs = base_qs
            elif sender_staff.is_hod or (sender_staff.is_head_of_unit and sender_staff.is_privileged_head):
                from organization.models import Department as Dept
                from organization.models import Unit

                pks = set()
                for d in Dept.objects.filter(head__isnull=False):
                    pks.add(d.head.pk)
                for u in Unit.objects.filter(head__isnull=False):
                    pks.add(u.head.pk)
                for s in base_qs.filter(is_supervisor=True):
                    pks.add(s.pk)
                pks.discard(sender_staff.pk)
                eligible_qs = base_qs.filter(pk__in=pks)
            elif sender_staff.is_supervisor:
                from organization.models import Department as Dept
                from organization.models import Unit

                pks = set()
                for d in Dept.objects.filter(head__isnull=False):
                    pks.add(d.head.pk)
                for u in Unit.objects.filter(head__isnull=False):
                    pks.add(u.head.pk)
                eligible_qs = base_qs.filter(pk__in=pks)
            else:
                # Lower staff (and pure heads-of-unit): direct head only,
                # walking up the hierarchy and skipping self.
                eligible_qs = base_qs.filter(pk__in=_reporting_hierarchy_pks(sender_staff))
        else:
            eligible_qs = base_qs

        recipients = eligible_qs.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(designation__name__icontains=query)
            | Q(department__name__icontains=query)
            | Q(unit__name__icontains=query)
            | Q(section__name__icontains=query)
            | Q(division__name__icontains=query)
        ).distinct()[:10]

        html = (
            '<div class="w-full mt-1 bg-white border border-slate-200 '
            'rounded-lg shadow-lg overflow-hidden max-h-64 overflow-y-auto">'
        )
        if recipients:
            for staff in recipients:
                name = staff.user.get_full_name() or staff.user.username
                email = staff.user.email or ""
                dept = staff.department.name if staff.department else ""
                unit = staff.unit.name if staff.unit else ""
                role_badge = ""
                if staff.is_md:
                    role_badge = (
                        '<span class="text-[8px] bg-red-100 text-red-700 '
                        'px-1.5 py-0.5 rounded font-bold uppercase">MD</span>'
                    )
                elif staff.is_hod:
                    role_badge = (
                        '<span class="text-[8px] bg-purple-100 text-purple-700 '
                        'px-1.5 py-0.5 rounded font-bold uppercase">HOD</span>'
                    )
                elif staff.is_head_of_unit:
                    role_badge = (
                        '<span class="text-[8px] bg-blue-100 text-blue-700 '
                        'px-1.5 py-0.5 rounded font-bold uppercase">Unit Mgr</span>'
                    )
                elif staff.is_supervisor:
                    role_badge = (
                        '<span class="text-[8px] bg-amber-100 text-amber-700 '
                        'px-1.5 py-0.5 rounded font-bold uppercase">Supervisor</span>'
                    )

                location_parts = [p for p in [unit, dept] if p]
                location = " · ".join(location_parts)

                safe_name = name.replace("'", "\\'")
                meta = staff.role_label
                safe_meta = meta.replace("'", "\\'")
                html += f"""
                <div class="px-4 py-3 hover:bg-slate-50 cursor-pointer
                            border-b border-slate-100 last:border-0 transition-colors"
                     @click="recipientId = '{staff.user.id}'; recipientLabel = '{safe_name} — {safe_meta}'; showResults = false">
                    <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                            <div class="flex items-center gap-1.5 flex-wrap">
                                <p class="text-xs font-bold text-slate-900">{name}</p>
                                {role_badge}
                            </div>
                            <p class="text-[10px] text-slate-500 font-medium truncate">{meta}</p>
                            <p class="text-[10px] text-slate-400 truncate">{email}</p>
                        </div>
                        <div class="text-right shrink-0">
                            <p class="text-[9px] text-slate-500 font-bold">{location}</p>
                        </div>
                    </div>
                </div>
                """
        else:
            html += (
                '<div class="px-4 py-3 text-xs text-slate-500 italic text-center">No eligible recipients found.</div>'
            )
        html += "</div>"

        return HttpResponse(html)


class UrgentCountView(LoginRequiredMixin, View):
    """HTMX endpoint to get urgent document count for sidebar badge."""

    def get(self, request, *args, **kwargs):
        staff = getattr(request.user, "staff", None)
        if not staff:
            return HttpResponse("")

        from document_management.models import Document, File
        from django.db.models import Q

        # Staff's accessible files (same logic as MyFilesView)
        file_qs = File.objects.filter(
            Q(owner=staff) | Q(created_by=request.user) | Q(current_location=staff)
        ).distinct()
        if not staff.is_registry:
            file_qs = file_qs.exclude(status__in=["inactive", "closed"])

        count = Document.objects.filter(
            Q(file__in=file_qs) | Q(file__isnull=True),
            priority__in=["urgent", "high"],
            status__in=["pending", "in_transit"]
        ).count()

        if count > 0:
            return HttpResponse(f"""
                <span id="urgent-count-badge"
                      class="ml-2 px-1.5 py-0.5 bg-red-600 text-white rounded-full text-[9px] font-black">
                    {count}
                </span>
            """)
        return HttpResponse("")


class InboxRecipientSearchView(LoginRequiredMixin, View):
    """Recipient search for inbox forward/approve.

    Normal requests follow the same routing rules as send-file.
    ``approvers_only=1`` instead returns just the staff who hold
    ``can_approve_document`` (the Medical Director role) — the only people a
    reviewer without approval rights can route their approval to — and skips
    the routing rules, because the approver may sit outside the sender's
    usual scope.
    """

    def get(self, request, *args, **kwargs):
        from document_management.permissions import can_manual_dispatch

        query = request.GET.get("q", "").strip()
        if not query or len(query) < 2:
            return HttpResponse("")

        sender_staff = getattr(request.user, "staff", None)
        base_qs = (
            Staff.objects.exclude(EXCLUDE_REGISTRY_Q)
            .exclude(user=request.user)
            .select_related("user", "designation", "department", "unit")
        )

        if request.GET.get("approvers_only"):
            from document_management.permissions import get_final_approvers

            eligible_qs = get_final_approvers(exclude_staff=sender_staff)
        else:
            eligible_qs = base_qs

        recipients = eligible_qs.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(designation__name__icontains=query)
            | Q(department__name__icontains=query)
            | Q(unit__name__icontains=query)
            | Q(section__name__icontains=query)
            | Q(division__name__icontains=query)
        ).distinct()[:10]

        html = (
            '<div class="w-full mt-1 bg-white border border-slate-200 '
            'rounded-lg shadow-lg overflow-hidden max-h-64 overflow-y-auto">'
        )
        if recipients:
            for staff in recipients:
                name = staff.user.get_full_name() or staff.user.username
                email = staff.user.email or ""
                unit = staff.unit.name if staff.unit else ""
                dept = staff.department.name if staff.department else ""
                location = " · ".join(p for p in [unit, dept] if p)
                role_badge = ""
                if staff.is_hod:
                    role_badge = (
                        '<span class="text-[8px] bg-purple-100 text-purple-700 '
                        'px-1.5 py-0.5 rounded font-bold uppercase">HOD</span>'
                    )
                elif staff.is_head_of_unit:
                    role_badge = (
                        '<span class="text-[8px] bg-blue-100 text-blue-700 '
                        'px-1.5 py-0.5 rounded font-bold uppercase">Unit Mgr</span>'
                    )
                elif staff.is_supervisor:
                    role_badge = (
                        '<span class="text-[8px] bg-amber-100 text-amber-700 '
                        'px-1.5 py-0.5 rounded font-bold uppercase">Supervisor</span>'
                    )

                meta = staff.role_label
                html += f"""
                <div class="px-4 py-3 hover:bg-slate-50 cursor-pointer
                            border-b border-slate-100 last:border-0
                            transition-colors inbox-recipient-option"
                     data-id="{staff.pk}" data-name="{name} — {meta}" data-meta="{meta}">
                    <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                            <div class="flex items-center gap-1.5 flex-wrap">
                                <p class="text-xs font-bold text-slate-900">{name}</p>
                                {role_badge}
                            </div>
                            <p class="text-[10px] text-slate-500 font-medium truncate">{meta}</p>
                            <p class="text-[10px] text-slate-400 truncate">{email}</p>
                        </div>
                        <div class="text-right shrink-0">
                            <p class="text-[9px] text-slate-500 font-bold">{location}</p>
                        </div>
                    </div>
                </div>
                """
        else:
            html += (
                '<div class="px-4 py-3 text-xs text-slate-500 italic text-center">No eligible recipients found.</div>'
            )
        html += "</div>"
        return HttpResponse(html)


class StaffSearchView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()

        queryset = Staff.objects.all()
        queryset = queryset.exclude(user__is_superuser=True)
        queryset = queryset.exclude(EXCLUDE_REGISTRY_Q)

        if query:
            queryset = queryset.filter(
                Q(user__username__icontains=query)
                | Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__email__icontains=query)
                | Q(department__name__icontains=query)
            )

        staff_members = queryset.select_related("user", "department", "designation", "unit").order_by(
            "user__first_name"
        )[:10]

        # Currently-picked user (Send Note keeps it in the hidden recipient
        # input) so reopening the modal shows their row as Selected.
        selected = (request.GET.get("recipient") or request.GET.get("selected") or "").strip()

        return render(
            request,
            "document_management/partials/staff_search_results.html",
            {"staff_members": staff_members, "query": query, "selected": selected},
        )


class UnitsForDepartmentView(LoginRequiredMixin, View):
    """HTMX: return <option> elements for units belonging to a department."""

    def get(self, request, *args, **kwargs):
        dept_id = request.GET.get("department")
        units = Unit.objects.filter(department_id=dept_id).order_by("name") if dept_id else Unit.objects.none()
        html = '<option value="">— No specific unit —</option>'
        for unit in units:
            html += f'<option value="{unit.pk}">{unit.name}</option>'
        return HttpResponse(html)
