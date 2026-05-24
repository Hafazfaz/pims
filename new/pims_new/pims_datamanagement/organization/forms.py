from django import forms

from .models import Department, Designation, Division, Section, Unit


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "code", "head"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["head"].required = False
        self.fields["head"].empty_label = "— None —"


class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ["name", "department", "division", "section", "head"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["head"].required = False
        self.fields["head"].empty_label = "— None —"
        self.fields["division"].required = False
        self.fields["division"].empty_label = "— None (optional) —"
        self.fields["section"].required = False
        self.fields["section"].empty_label = "— None (optional) —"


class DesignationForm(forms.ModelForm):
    class Meta:
        model = Designation
        fields = ["name", "level"]


class DivisionForm(forms.ModelForm):
    class Meta:
        model = Division
        fields = ["name", "department", "head"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["head"].required = False
        self.fields["head"].empty_label = "— None —"


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ["name", "department", "head"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["head"].required = False
        self.fields["head"].empty_label = "— None —"
