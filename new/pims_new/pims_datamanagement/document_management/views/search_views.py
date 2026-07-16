from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render
from django.views.generic import View
from organization.models import Staff, Unit

from .base import EXCLUDE_REGISTRY_Q


class UrgentCountView(LoginRequiredMixin, View):
    """HTMX endpoint to get urgent document count for sidebar badge."""

    def get(self, request, *args, **kwargs):
        staff = getattr(request.user, "staff", None)
        if not staff:
            return HttpResponse("")

        # Get urgent documents in active files accessible to this user
        from document_management.models import Document, File
        from django.db.models import Q

        user_files = File.objects.filter(
            Q(current_location=staff) |
            Q(owner=staff) |
            Q(department=staff.department) if staff.department else Q(),
            status="active"
        ).distinct()

        count = Document.objects.filter(
            file__in=user_files,
            priority__in=["urgent", "high"],
            status__in=["pending", "in_transit"]
        ).count()

        if count > 0:
            return HttpResponse(f"""
                <span class="ml-2 px-1.5 py-0.5 bg-red-500 text-white rounded-full text-[9px] font-black">
                    {count}
                </span>
            """)
        return HttpResponse("")


class RecipientSearchView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
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
            elif sender_staff.is_hod or sender_staff.is_head_of_unit:
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
                allowed_pks = []
                if sender_staff.unit and sender_staff.unit.head:
                    allowed_pks.append(sender_staff.unit.head.pk)
                elif sender_staff.department and sender_staff.department.head:
                    allowed_pks.append(sender_staff.department.head.pk)
                eligible_qs = base_qs.filter(pk__in=allowed_pks)
        else:
            eligible_qs = base_qs

        recipients = eligible_qs.filter(
            Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(department__name__icontains=query)
            | Q(unit__name__icontains=query)
        ).distinct()[:10]

        html = (
            '<div class="w-full mt-1 bg-white border border-slate-200 '
            'rounded-lg shadow-lg overflow-hidden max-h-64 overflow-y-auto">'
        )
        if recipients:
            for staff in recipients:
                name = staff.user.get_full_name() or staff.user.username
                email = staff.user.email or ""
                designation = staff.designation.name if staff.designation else ""
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
                html += f"""
                <div class="px-4 py-3 hover:bg-slate-50 cursor-pointer
                            border-b border-slate-100 last:border-0 transition-colors"
                     @click="recipientId = '{staff.user.id}'; recipientLabel = '{safe_name}'; showResults = false">
                    <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                            <div class="flex items-center gap-1.5 flex-wrap">
                                <p class="text-xs font-bold text-slate-900">{name}</p>
                                {role_badge}
                            </div>
                            <p class="text-[10px] text-slate-500 font-medium truncate">{designation}</p>
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

        from document_management.models import Document
        from django.db.models import Q

        # Staff's accessible files (same logic as MyFilesView)
        file_qs = File.objects.filter(
            Q(owner=staff) | Q(created_by=request.user) | Q(current_location=staff)
        ).distinct()
        if not staff.is_registry:
            file_qs = file_qs.exclude(status__in=["inactive", "closed"])

        count = Document.objects.filter(
            file__in=file_qs,
            priority__in=["urgent", "high"],
            status__in=["pending", "in_transit"]
        ).count()

        if count > 0:
            return HttpResponse(f"""
                <span id="urgent-count-badge"
                      class="ml-2 px-1.5 py-0.5 bg-red-600 text-white text-[8px] font-black rounded-full">
                    {count}
                </span>
            """)
        return HttpResponse("")


class InboxRecipientSearchView(LoginRequiredMixin, View):
    """Recipient search for inbox forward — applies same routing rules as send file."""

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        if not query or len(query) < 2:
            return HttpResponse("")

        sender_staff = getattr(request.user, "staff", None)
        base_qs = (
            Staff.objects.exclude(EXCLUDE_REGISTRY_Q)
            .exclude(user=request.user)
            .select_related("user", "designation", "department", "unit")
        )

        # Same routing rules as send handler
        if sender_staff:
            if sender_staff.is_md or sender_staff.is_executive:
                eligible_qs = base_qs
            elif sender_staff.is_hod or sender_staff.is_head_of_unit:
                # Any HOD, any head of unit, any supervisor
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
                allowed_pks = []
                if sender_staff.unit and sender_staff.unit.head:
                    allowed_pks.append(sender_staff.unit.head.pk)
                elif sender_staff.department and sender_staff.department.head:
                    allowed_pks.append(sender_staff.department.head.pk)
                eligible_qs = base_qs.filter(pk__in=allowed_pks)
        else:
            eligible_qs = base_qs

        recipients = eligible_qs.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(designation__name__icontains=query)
            | Q(unit__name__icontains=query)
        ).distinct()[:10]

        html = (
            '<div class="w-full mt-1 bg-white border border-slate-200 '
            'rounded-lg shadow-lg overflow-hidden max-h-64 overflow-y-auto">'
        )
        if recipients:
            for staff in recipients:
                name = staff.user.get_full_name() or staff.user.username
                email = staff.user.email or ""
                designation = staff.designation.name if staff.designation else ""
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

                html += f"""
                <div class="px-4 py-3 hover:bg-slate-50 cursor-pointer
                            border-b border-slate-100 last:border-0
                            transition-colors inbox-recipient-option"
                     data-id="{staff.pk}" data-name="{name}">
                    <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                            <div class="flex items-center gap-1.5 flex-wrap">
                                <p class="text-xs font-bold text-slate-900">{name}</p>
                                {role_badge}
                            </div>
                            <p class="text-[10px] text-slate-500 font-medium truncate">{designation}</p>
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

        return render(
            request,
            "document_management/partials/staff_search_results.html",
            {"staff_members": staff_members, "query": query},
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
