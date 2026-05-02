from django import forms
from .models import Department, Unit, Designation


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'head']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['head'].required = False
        self.fields['head'].empty_label = '— None —'


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['name', 'department', 'head']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['head'].required = False
        self.fields['head'].empty_label = '— None —'


class DesignationForm(forms.ModelForm):
    class Meta:
        model = Designation
        fields = ['name', 'level']
