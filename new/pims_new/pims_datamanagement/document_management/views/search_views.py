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

        recipients = Staff.objects.filter(
            Q(headed_department__isnull=False) | Q(headed_unit__isnull=False)
        ).filter(
            Q(user__username__icontains=query) |
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(department__name__icontains=query) |
            Q(unit__name__icontains=query)
        ).exclude(user=request.user).distinct()[:10]

        html = '<div class="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg overflow-hidden max-h-60 overflow-y-auto">'
        if recipients:
            for staff in recipients:
                name = staff.user.get_full_name() or staff.user.username
                designation = staff.designation.name if staff.designation else "Staff"
                role_label = ""
                if staff.is_hod:
                    role_label = '<span class="ml-2 text-[9px] bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded font-bold uppercase">HOD</span>'
                elif staff.is_unit_manager:
                     role_label = '<span class="ml-2 text-[9px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-bold uppercase">Manager</span>'

                dept_code = staff.department.code if staff.department else 'N/A'
                
                html += f"""
                <div class="px-4 py-3 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0 transition-colors"
                     @click="$dispatch('recipient-selected', {{ id: '{staff.user.id}', username: '{name}' }})">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs font-bold text-slate-900">{name} {role_label}</p>
                            <p class="text-[10px] text-slate-500 font-medium">{designation}</p>
                        </div>
                        <div class="text-right">
                             <p class="text-[9px] text-slate-400 font-bold uppercase tracking-wider">{dept_code}</p>
                        </div>
                    </div>
                </div>
                """
        else:
            html += '<div class="px-4 py-3 text-xs text-slate-500 italic text-center">No matching HODs or Managers found.</div>'
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
