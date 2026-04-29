from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.shortcuts import render
from django.http import HttpResponse
from django.db.models import Q
from organization.models import Staff
from .base import EXCLUDE_REGISTRY_Q

class RecipientSearchView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        if not query or len(query) < 2:
            return HttpResponse("")

        sender_staff = getattr(request.user, 'staff', None)
        base_qs = Staff.objects.exclude(EXCLUDE_REGISTRY_Q).exclude(user=request.user).select_related(
            'user', 'designation', 'department', 'unit', 'headed_unit', 'headed_department'
        )

        if sender_staff:
            if sender_staff.is_md or sender_staff.is_executive:
                eligible_qs = base_qs
            elif sender_staff.is_hod or sender_staff.is_head_of_unit:
                from organization.models import Department as Dept, Unit
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
                from organization.models import Department as Dept, Unit
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
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(department__name__icontains=query) |
            Q(unit__name__icontains=query)
        ).distinct()[:10]

        html = '<div class="w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden max-h-64 overflow-y-auto">'
        if recipients:
            for staff in recipients:
                name = staff.user.get_full_name() or staff.user.username
                email = staff.user.email or ''
                designation = staff.designation.name if staff.designation else ''
                dept = staff.department.name if staff.department else ''
                unit = staff.unit.name if staff.unit else ''
                role_badge = ''
                if staff.is_md:
                    role_badge = '<span class="text-[8px] bg-red-100 text-red-700 px-1.5 py-0.5 rounded font-bold uppercase">MD</span>'
                elif staff.is_hod:
                    role_badge = '<span class="text-[8px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded font-bold uppercase">HOD</span>'
                elif staff.is_head_of_unit:
                    role_badge = '<span class="text-[8px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-bold uppercase">Unit Mgr</span>'
                elif staff.is_supervisor:
                    role_badge = '<span class="text-[8px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-bold uppercase">Supervisor</span>'

                location_parts = [p for p in [unit, dept] if p]
                location = ' · '.join(location_parts)

                html += f"""
                <div class="px-4 py-3 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0 transition-colors"
                     @click="recipientId = '{staff.user.id}'; recipientLabel = '{name.replace("'", "\\'")}'; showResults = false">
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
            html += '<div class="px-4 py-3 text-xs text-slate-500 italic text-center">No eligible recipients found.</div>'
        html += '</div>'

        return HttpResponse(html)

class InboxRecipientSearchView(LoginRequiredMixin, View):
    """Recipient search for inbox forward — applies same routing rules as send file."""
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        if not query or len(query) < 2:
            return HttpResponse("")

        sender_staff = getattr(request.user, 'staff', None)
        base_qs = Staff.objects.exclude(EXCLUDE_REGISTRY_Q).exclude(user=request.user).select_related(
            'user', 'designation', 'department', 'unit'
        )

        # Same routing rules as send handler
        if sender_staff:
            if sender_staff.is_md or sender_staff.is_executive:
                eligible_qs = base_qs
            elif sender_staff.is_hod or sender_staff.is_head_of_unit:
                # Any HOD, any head of unit, any supervisor
                from organization.models import Department as Dept, Unit
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
                from organization.models import Department as Dept, Unit
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
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__email__icontains=query) |
            Q(designation__name__icontains=query) |
            Q(unit__name__icontains=query)
        ).distinct()[:10]

        html = '<div class="w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden max-h-64 overflow-y-auto">'
        if recipients:
            for staff in recipients:
                name = staff.user.get_full_name() or staff.user.username
                email = staff.user.email or ''
                designation = staff.designation.name if staff.designation else ''
                unit = staff.unit.name if staff.unit else ''
                dept = staff.department.name if staff.department else ''
                location = ' · '.join(p for p in [unit, dept] if p)
                role_badge = ''
                if staff.is_hod:
                    role_badge = '<span class="text-[8px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded font-bold uppercase">HOD</span>'
                elif staff.is_head_of_unit:
                    role_badge = '<span class="text-[8px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-bold uppercase">Unit Mgr</span>'
                elif staff.is_supervisor:
                    role_badge = '<span class="text-[8px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-bold uppercase">Supervisor</span>'

                html += f"""
                <div class="px-4 py-3 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0 transition-colors inbox-recipient-option"
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
            html += '<div class="px-4 py-3 text-xs text-slate-500 italic text-center">No eligible recipients found.</div>'
        html += '</div>'
        return HttpResponse(html)


class StaffSearchView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        
        queryset = Staff.objects.all()
        queryset = queryset.exclude(user__is_superuser=True)
        queryset = queryset.exclude(EXCLUDE_REGISTRY_Q)

        if query:
            queryset = queryset.filter(
                Q(user__username__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(department__name__icontains=query)
            )
        
        staff_members = queryset.select_related('user', 'department', 'designation').order_by('user__first_name')[:10]

        return render(request, 'document_management/partials/staff_search_results.html', {
            'staff_members': staff_members,
            'query': query
        })
