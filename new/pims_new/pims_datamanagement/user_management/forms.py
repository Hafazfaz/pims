from django import forms
from django.contrib.auth import get_user_model
from organization.models import StaffSignature, Department, Unit, Designation

CustomUser = get_user_model()

class SignatureUploadForm(forms.ModelForm):
    signature_data = forms.CharField(required=True, widget=forms.HiddenInput())

    class Meta:
        model = StaffSignature
        fields = []  # We don't use 'image' directly from the form anymore

class UserCreateForm(forms.ModelForm):
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=True)
    unit = forms.ModelChoiceField(queryset=Unit.objects.none(), required=False) # Unit could be dependent on Department
    designation = forms.ModelChoiceField(queryset=Designation.objects.all(), required=True)
    staff_type = forms.ChoiceField(choices=[('permanent', 'Permanent'), ('contract', 'Contract')], required=True)

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'first_name', 'last_name']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'department' in self.data:
            try:
                department_id = int(self.data.get('department'))
                self.fields['unit'].queryset = Unit.objects.filter(department_id=department_id)
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and hasattr(self.instance, 'staff') and self.instance.staff.department:
            self.fields['unit'].queryset = self.instance.staff.department.units.all()
        else:
            self.fields['unit'].queryset = Unit.objects.all()
