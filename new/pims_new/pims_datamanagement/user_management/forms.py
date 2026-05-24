from django import forms
from django.contrib.auth import get_user_model
from organization.models import Department, Designation, Division, Section, StaffSignature, Unit

CustomUser = get_user_model()


class SignatureUploadForm(forms.ModelForm):
    signature_data = forms.CharField(required=False, widget=forms.HiddenInput())
    image = forms.ImageField(required=False, label="Upload Signature Image")

    class Meta:
        model = StaffSignature
        fields = []


class UserCreateForm(forms.ModelForm):
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=True)
    division = forms.ModelChoiceField(
        queryset=Division.objects.none(), required=False, empty_label="— None (optional) —"
    )
    section = forms.ModelChoiceField(queryset=Section.objects.none(), required=False, empty_label="— None (optional) —")
    unit = forms.ModelChoiceField(queryset=Unit.objects.none(), required=False)
    designation = forms.ModelChoiceField(queryset=Designation.objects.all(), required=True)
    staff_type = forms.ChoiceField(choices=[("permanent", "Permanent"), ("contract", "Contract")], required=True)
    is_supervisor = forms.BooleanField(required=False)
    password = forms.CharField(widget=forms.PasswordInput, required=True)

    class Meta:
        model = CustomUser
        fields = ["username", "email", "first_name", "last_name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "department" in self.data:
            try:
                department_id = int(self.data.get("department"))
                self.fields["unit"].queryset = Unit.objects.filter(department_id=department_id)
                self.fields["division"].queryset = Division.objects.filter(department_id=department_id)
                self.fields["section"].queryset = Section.objects.filter(department_id=department_id)
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and hasattr(self.instance, "staff") and self.instance.staff.department:
            self.fields["unit"].queryset = self.instance.staff.department.units.all()
            self.fields["division"].queryset = self.instance.staff.department.divisions.all()
            self.fields["section"].queryset = Section.objects.filter(department=self.instance.staff.department)
        else:
            self.fields["unit"].queryset = Unit.objects.all()
            self.fields["division"].queryset = Division.objects.all()
            self.fields["section"].queryset = Section.objects.all()
