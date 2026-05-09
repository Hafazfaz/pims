from django import forms
from django.db.models import Q
from organization.models import Staff, Unit, Division
from user_management.models import CustomUser


from .models import Document, DocumentType, File, FileAccessRequest


class FileForm(forms.ModelForm):
    class Meta:
        model = File
        fields = ["title", "file_type", "owner", "department", "division", "unit", "external_party"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter folder title...",
                }
            ),
            "file_type": forms.Select(attrs={"class": "form-select", "x-model": "fileType"}),
            "owner": forms.HiddenInput(),
            "department": forms.Select(attrs={"class": "form-select"}),
            "division": forms.Select(attrs={"class": "form-select"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "external_party": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., Ministry of Health, WHO, etc.",
                }
            ),
        }
        labels = {
            "title": "Folder Title",
            "file_type": "Folder Category",
            "owner": "Associated Staff",
            "department": "Associated Department",
            "division": "Associated Division",
            "unit": "Associated Unit",
            "external_party": "External Organization/Party",
        }

    policy_type = forms.ChoiceField(
        choices=[("internal", "Departmental"), ("external", "Corporate/External")],
        required=False,
        initial="internal",
        widget=forms.RadioSelect(attrs={"class": "flex space-x-6", "x-model": "policyType"}),
        label="Policy Range"
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Unit starts empty; populated via HTMX when department is selected
        self.fields["unit"].queryset = Unit.objects.none()
        self.fields["unit"].required = False
        self.fields["division"].queryset = Division.objects.none()
        self.fields["division"].required = False

        # If editing and department is set, populate units for that department
        if self.instance and self.instance.pk and self.instance.department_id:
            self.fields["unit"].queryset = Unit.objects.filter(department=self.instance.department)
        # Also handle POST data
        elif "department" in (self.data or {}):
            try:
                dept_id = int(self.data["department"])
                self.fields["unit"].queryset = Unit.objects.filter(department_id=dept_id)
            except (ValueError, TypeError):
                pass

        if self.user and self.user.is_authenticated:
            try:
                creator_staff = self.user.staff
                if creator_staff.is_registry:
                    self.fields["owner"].queryset = Staff.objects.exclude(
                        designation__name__icontains="registry"
                    ).order_by("user__username")
                elif creator_staff.is_hod:
                    self.fields["owner"].queryset = Staff.objects.filter(
                        department=creator_staff.headed_department
                    ).exclude(user=self.user).order_by("user__username")
                elif creator_staff.is_unit_manager:
                    self.fields["owner"].queryset = Staff.objects.filter(
                        unit=creator_staff.headed_unit
                    ).exclude(user=self.user).order_by("user__username")
                else:
                    self.fields["owner"].queryset = Staff.objects.filter(user=self.user)

                self.fields["owner"].widget = forms.HiddenInput()
                if not creator_staff.is_registry and not creator_staff.is_hod and not creator_staff.is_unit_manager:
                    self.fields["owner"].initial = creator_staff
                self.fields["owner"].required = False
            except Staff.DoesNotExist:
                self.fields["owner"].queryset = Staff.objects.filter(user=self.user)
        else:
            self.fields["owner"].queryset = Staff.objects.none()

    def clean_title(self):
        title = self.cleaned_data["title"]
        return title.upper()  # Enforce uppercase for title

    def clean(self):
        cleaned_data = super().clean()
        file_type = cleaned_data.get("file_type")
        owner = cleaned_data.get("owner")
        department = cleaned_data.get("department")
        unit = cleaned_data.get("unit")
        external_party = cleaned_data.get("external_party")
        policy_range = cleaned_data.get("policy_type")

        if file_type == "personal":
            if not owner:
                raise forms.ValidationError({"owner": "Personal folders must be assigned to a staff member."})
            existing = File.objects.filter(file_type="personal", owner=owner)
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    f"A personal record folder already exists for {owner}. Only one personal folder is allowed per staff member."
                )
            cleaned_data["department"] = None
            cleaned_data["unit"] = None
            cleaned_data["external_party"] = None

        elif file_type == "policy":
            if policy_range == "internal":
                if not department:
                    raise forms.ValidationError({"department": "Please select a department for this internal policy folder."})
                # Validate unit belongs to selected department
                if unit and unit.department != department:
                    raise forms.ValidationError({"unit": "Selected unit does not belong to the chosen department."})
                cleaned_data["external_party"] = None
            else:
                if not external_party:
                    raise forms.ValidationError({"external_party": "Please specify the external organization or party name."})
                cleaned_data["department"] = None
                cleaned_data["unit"] = None
            cleaned_data["owner"] = None

        return cleaned_data


class DocumentForm(forms.ModelForm):
    send_to = forms.ModelChoiceField(
        queryset=Staff.objects.all(),
        required=False,
        label="Send To (Route File)",
        help_text="Optionally route this file to another staff member for review or approval.",
        widget=forms.Select(attrs={"class": "form-select"})
    )
    document_type = forms.ModelChoiceField(
        queryset=DocumentType.objects.all(),
        required=True,
        label="Document Type",
        empty_label="— Select type —",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Document
        fields = ["title", "document_type", "minute_content", "attachment", "parent"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Minute Subject/Title (e.g. APPLICATION FOR LEAVE)",
                }
            ),
            "parent": forms.HiddenInput(),
            "minute_content": forms.Textarea(
                attrs={
                    "class": "form-control summernote",
                    "rows": 10,
                    "placeholder": "Enter minute content...",
                }
            ),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
        }
        labels = {
            "title": "Subject",
            "minute_content": "Minute Content",
            "attachment": "Upload Attachment",
        }

    include_signature = forms.BooleanField(
        required=False,
        label="Attach Digital Signature",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"})
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
        # Only HODs or Unit Managers can see the signature checkbox
        can_sign = False
        if self.user and hasattr(self.user, 'staff'):
            staff = self.user.staff
            if staff.is_hod or staff.is_unit_manager or staff.is_registry:
                can_sign = True
        
        if not can_sign:
            self.fields.pop('include_signature', None)

    def clean(self):
        cleaned_data = super().clean()
        minute_content = cleaned_data.get("minute_content")
        attachment = cleaned_data.get("attachment")

        if not minute_content and not attachment:
            raise forms.ValidationError(
                "Please provide either minute content or an attachment."
            )

        return cleaned_data



class SendFileForm(forms.Form):
    recipient = forms.ModelChoiceField(
        queryset=CustomUser.objects.none(),
        empty_label="Select Recipient",
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Send to",
    )
    note = forms.CharField(
        required=False,
        label="Covering Note",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    movement_attachment = forms.FileField(
        required=False,
        label="Covering Memo / Dispatch Note",
        widget=forms.FileInput(attrs={"class": "form-control"}),
    )
    reference_documents = forms.ModelMultipleChoiceField(
        queryset=Document.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Reference Documents",
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        file_obj = kwargs.pop("file_obj", None)
        document = kwargs.pop("document", None)
        staff = kwargs.pop("staff", None)
        super().__init__(*args, **kwargs)

        if self.user and self.user.is_authenticated:
            from document_management.views.base import EXCLUDE_REGISTRY_Q
            base_qs = Staff.objects.exclude(EXCLUDE_REGISTRY_Q).exclude(user=self.user).select_related('user')

            if staff:
                if staff.is_registry:
                    eligible = base_qs
                elif staff.is_hod or staff.is_md or staff.is_executive:
                    eligible = base_qs
                elif staff.is_effective_supervisor and (not file_obj or file_obj.owner != staff):
                    # Supervisor sending someone else's file → other supervisors + direct heads
                    supervisor_pks = [s.pk for s in base_qs if s.is_effective_supervisor]
                    direct_head_pks = []
                    if staff.unit and staff.unit.head:
                        direct_head_pks.append(staff.unit.head.pk)
                    if staff.department and staff.department.head:
                        direct_head_pks.append(staff.department.head.pk)
                    eligible = base_qs.filter(pk__in=set(supervisor_pks + direct_head_pks))
                else:
                    # Regular staff OR supervisor sending their own file → unit manager if exists, else HOD
                    if staff.unit and staff.unit.head:
                        eligible = base_qs.filter(pk=staff.unit.head.pk)
                    elif staff.department and staff.department.head:
                        eligible = base_qs.filter(pk=staff.department.head.pk)
                    else:
                        eligible = base_qs.none()
            else:
                eligible = base_qs

            self.fields['recipient'].queryset = CustomUser.objects.filter(
                staff__in=eligible
            ).order_by('last_name', 'first_name')
        else:
            self.fields['recipient'].queryset = CustomUser.objects.none()

        if file_obj and document:
            self.fields['reference_documents'].queryset = file_obj.documents.exclude(pk=document.pk).order_by('-uploaded_at')

class FileUpdateForm(forms.ModelForm):
    class Meta:
        model = File
        fields = ["title"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter file title (e.g., PERSONNEL FILE OF JOHN DOE)",
                }
            ),
        }
        labels = {
            "title": "File Title",
        }

    def clean_title(self):
        title = self.cleaned_data["title"]
        return title.upper()  # Enforce uppercase for title

class DocumentUploadForm(forms.ModelForm):
    # This form allows uploading an attachment to an existing file
    file = forms.ModelChoiceField(
        queryset=File.objects.all().order_by('title'),
        empty_label="Select a File",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Associate with File",
    )
    document_type = forms.ModelChoiceField(
        queryset=DocumentType.objects.all(),
        required=True,
        label="Document Type",
        empty_label="— Select type —",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    minute_content = forms.CharField(
        required=False,
        label="Minute / Note Content",
        widget=forms.Textarea(attrs={"class": "form-control summernote", "rows": 6}),
    )

    class Meta:
        model = Document
        fields = ["file", "title", "document_type", "minute_content", "attachment"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g., MSc Degree Certificate, Appraisal Form, etc.",
                }
            ),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
        }
        labels = {
            "title": "Document Title/Label",
            "attachment": "Upload Document",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Filter files that the current user has access to for association
        if self.user and self.user.is_authenticated:
            try:
                staff_user = Staff.objects.get(user=self.user)
                if staff_user.is_registry:
                    # Registry can upload documents to ANY file
                    self.fields['file'].queryset = File.objects.all().order_by('title')
                else:
                    # Users can upload documents to files they own or are currently at their location
                    self.fields['file'].queryset = File.objects.filter(
                        Q(owner=staff_user) | Q(current_location=staff_user)
                    ).order_by('title')
            except Staff.DoesNotExist:
                # If not a staff user, no files to select (shouldn't happen with LoginRequiredMixin)
                self.fields['file'].queryset = File.objects.none()
        else:
            self.fields['file'].queryset = File.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        attachment = cleaned_data.get("attachment")
        minute_content = cleaned_data.get("minute_content")
        if not attachment and not minute_content:
            raise forms.ValidationError("Please provide either a document upload or minute content.")
        return cleaned_data

class FileAccessRequestForm(forms.ModelForm):
    class Meta:
        model = FileAccessRequest
        fields = ["access_type", "reason"]
        widgets = {
            "access_type": forms.RadioSelect(
                attrs={"class": "form-check-input"}
            ),
            "reason": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "State your reason for requesting access to the original file...",
                }
            ),
        }
        labels = {
            "access_type": "Access Type",
            "reason": "Reason for Access",
        }
        help_texts = {
            "access_type": "Read-Only: View and download only | Read-Write: Add/remove documents",
        }
