from django import forms
from .models import Department, Unit, Designation, Division


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
        fields = ['name', 'department', 'division', 'head']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['head'].required = False
        self.fields['head'].empty_label = '— None —'
        self.fields['division'].required = False
        self.fields['division'].empty_label = '— None (optional) —'


class DesignationForm(forms.ModelForm):
    class Meta:
        model = Designation
        fields = ['name', 'level']


class DivisionForm(forms.ModelForm):
    class Meta:
        model = Division
        fields = ['name', 'department']
