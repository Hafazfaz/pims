from django import forms
from organization.models import Department, Staff, Unit
from user_management.models import CustomUser


from .models import Document, File, FileAccessRequest


class FileForm(forms.ModelForm):
    attachments = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control"}),
        required=False,
        help_text="You can upload one initial document.",
    )

    class Meta:
        model = File
        fields = ["title", "file_type", "owner", "department", "external_party"] 
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
        self.user = kwargs.pop("user", None)  # Get the user and remove from kwargs
        super().__init__(*args, **kwargs)
        
        # Insert policy_type after file_type
        # (This is just for ordering in some layouts, but template will handle it)
        
        # Filter owner queryset based on user's permissions
        if self.user and self.user.is_authenticated:
            try:
                creator_staff = self.user.staff
                
                # Default logic for owner filtering remains same for now, 
                # but we will enforce 1:1 in clean()
                if creator_staff.is_hod:
                    # HOD can create files for anyone in their department EXCEPT themselves
                    self.fields["owner"].queryset = Staff.objects.filter(
                        department=creator_staff.headed_department
                    ).exclude(user=self.user).order_by("user__username")
                elif creator_staff.is_unit_manager:
                    # Unit Manager can create files for anyone in their unit EXCEPT themselves
                    self.fields["owner"].queryset = Staff.objects.filter(
                        unit=creator_staff.headed_unit
                    ).exclude(user=self.user).order_by("user__username")
                else:
                    # Regular user can only create files for themselves
                    self.fields["owner"].queryset = Staff.objects.filter(user=self.user)
                
                # Always hide owner since template uses custom display
                self.fields["owner"].widget = forms.HiddenInput()
                # Set initial value (current user for staff, or blank for registry/hod if they need to choose)
                if not creator_staff.is_registry and not creator_staff.is_hod and not creator_staff.is_unit_manager:
                    self.fields["owner"].initial = creator_staff
            except Staff.DoesNotExist:
                # If user is not staff, they can only create for themselves
                self.fields["owner"].queryset = Staff.objects.filter(
                    user=self.user
                )

            # Registry User Exception: Can assign to anyone (but initially show empty or self)
            # We will rely on the clean method to validate the final selection
            # and the frontend to search.
                if creator_staff.is_registry:
                     # For registry, we allow all staff in the queryset
                     self.fields["owner"].queryset = Staff.objects.all()
                
                # Ensure it's not required by browser if it's hidden (Django validation will still run)
                # Actually, HiddenInput doesn't render 'required' in modern Django, but safety first.
                self.fields["owner"].required = False 

        else:
            # For unauthenticated users, no owner choices (shouldn't happen with LoginRequiredMixin)
            self.fields["owner"].queryset = Staff.objects.none()

    def clean_title(self):
        title = self.cleaned_data["title"]
        return title.upper()  # Enforce uppercase for title

    def clean(self):
        cleaned_data = super().clean()
        file_type = cleaned_data.get("file_type")
        owner = cleaned_data.get("owner")
        department = cleaned_data.get("department")
        external_party = cleaned_data.get("external_party")
        policy_range = cleaned_data.get("policy_type")

        # Validation for Personal Folders
        if file_type == "personal":
            if not owner:
                raise forms.ValidationError({"owner": "Personal folders must be assigned to a staff member."})
            
            # Enforce 1:1 restriction
            existing = File.objects.filter(file_type="personal", owner=owner)
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            
            if existing.exists():
                raise forms.ValidationError(
                    f"A personal record folder already exists for {owner}. Only one personal folder is allowed per staff member."
                )
            
            # Clear policy fields for personal type
            cleaned_data["department"] = None
            cleaned_data["external_party"] = None

        # Validation for Policy Folders
        elif file_type == "policy":
            if policy_range == "internal":
                if not department:
                    raise forms.ValidationError({"department": "Please select a department for this internal policy folder."})
                cleaned_data["external_party"] = None
            else:
                if not external_party:
                    raise forms.ValidationError({"external_party": "Please specify the external organization or party name."})
                cleaned_data["department"] = None
            
            cleaned_data["owner"] = None

        return cleaned_data


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "minute_content", "attachment", "parent"]
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


from django.db.models import Q

class SendFileForm(forms.Form):
    recipient = forms.ModelChoiceField(
        queryset=CustomUser.objects.all().order_by("username"),
        empty_label="Select Recipient",
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Send to",
    )
    document_id = forms.IntegerField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if self.user and self.user.is_authenticated:
            is_unit_manager = Q(staff__headed_unit__isnull=False)
            is_hod = Q(staff__headed_department__isnull=False)
            
            self.fields['recipient'].queryset = CustomUser.objects.filter(
                is_unit_manager | is_hod
            ).exclude(pk=self.user.pk).order_by("username").distinct()
        else:
            # For unauthenticated users, no recipients
            self.fields['recipient'].queryset = CustomUser.objects.none()

    def clean_recipient(self):
        recipient = self.cleaned_data.get('recipient')
        if recipient not in self.fields['recipient'].queryset:
            raise forms.ValidationError("Invalid recipient. Please select a valid user from the list.")
        return recipient

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
        queryset=File.objects.all().order_by('title'), # Users will select from existing files
        empty_label="Select a File",
        widget=forms.Select(attrs={"class": "form-control"}),
        label="Associate with File",
    )

    class Meta:
        model = Document
        fields = ["file", "title", "attachment"] # Allow labeling the document
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
                        models.Q(owner=staff_user) | models.Q(current_location=staff_user)
                    ).order_by('title')
            except Staff.DoesNotExist:
                # If not a staff user, no files to select (shouldn't happen with LoginRequiredMixin)
                self.fields['file'].queryset = File.objects.none()
        else:
            self.fields['file'].queryset = File.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        attachment = cleaned_data.get("attachment")

        if not attachment:
            raise forms.ValidationError(
                "Please upload an attachment."
            )
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
