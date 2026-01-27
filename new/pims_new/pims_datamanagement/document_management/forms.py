from django import forms
from organization.models import Department, Staff, Unit
from user_management.models import CustomUser


from .models import Document, File


class FileForm(forms.ModelForm):
    attachments = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control"}),
        required=False,
        help_text="You can upload one initial document.",
    )

    class Meta:
        model = File
        fields = ["title", "file_type", "owner"] 
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter file title (e.g., PERSONNEL FILE OF JOHN DOE)",
                }
            ),
            "file_type": forms.Select(attrs={"class": "form-select"}),
            "owner": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "title": "File Title",
            "file_type": "File Type",
            "owner": "File Owner",
        }  # Removed department label here

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)  # Get the user and remove from kwargs
        super().__init__(*args, **kwargs)

        # Filter owner queryset based on user's permissions
        if self.user and self.user.is_authenticated:
            try:
                creator_staff = self.user.staff
                is_hod = (
                    hasattr(creator_staff, "headed_department")
                    and creator_staff.headed_department is not None
                )
                is_unit_manager = (
                    hasattr(creator_staff, "headed_unit")
                    and creator_staff.headed_unit is not None
                )

                if is_hod:
                    # HOD can create files for anyone in their department
                    self.fields["owner"].queryset = Staff.objects.filter(
                        department=creator_staff.headed_department
                    ).order_by("user__username")
                elif is_unit_manager:
                    # Unit Manager can create files for anyone in their unit
                    self.fields["owner"].queryset = Staff.objects.filter(
                        unit=creator_staff.headed_unit
                    ).order_by("user__username")
                else:
                    # Regular user can only create files for themselves
                    self.fields["owner"].queryset = Staff.objects.filter(user=self.user)
            except Staff.DoesNotExist:
                # If user is not staff, they can only create for themselves
                self.fields["owner"].queryset = Staff.objects.filter(
                    user=self.user
                )
        else:
            # For unauthenticated users, no owner choices (shouldn't happen with LoginRequiredMixin)
            self.fields["owner"].queryset = Staff.objects.none()

    def clean_title(self):
        title = self.cleaned_data["title"]
        return title.upper()  # Enforce uppercase for title

    def clean(self):
        cleaned_data = super().clean()
        owner = cleaned_data.get("owner")  # This is a Staff object

        # Get the creator (current user) from the form's kwargs
        creator = self.user

        if not creator or not creator.is_authenticated:
            raise forms.ValidationError(
                "Creator information is missing or not authenticated."
            )

        try:
            creator_staff = creator.staff
        except Staff.DoesNotExist:
            raise forms.ValidationError(
                "Creator is not associated with a staff profile."
            )

        owner_staff = owner
        if not owner_staff:
            raise forms.ValidationError("Owner is required.")


        # Check if creator is an HOD
        is_hod = (
            hasattr(creator_staff, "headed_department")
            and creator_staff.headed_department is not None
        )
        is_unit_manager = (
            hasattr(creator_staff, "headed_unit")
            and creator_staff.headed_unit is not None
        )

        if is_hod:
            if owner_staff.department != creator_staff.headed_department:
                raise forms.ValidationError(
                    f"As a Department Head, you can only create files for staff within your department ({creator_staff.headed_department.name})."
                )
        elif is_unit_manager:
            if owner_staff.unit != creator_staff.headed_unit:
                raise forms.ValidationError(
                    f"As a Unit Manager, you can only create files for staff within your unit ({creator_staff.headed_unit.name})."
                )
        else:
            if owner.user != creator:
                raise forms.ValidationError("You can only create files for yourself.")

        return cleaned_data


class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["minute_content", "attachment", "parent"]
        widgets = {
            "parent": forms.HiddenInput(),
            "minute_content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 10,
                    "placeholder": "Enter minute content...",
                }
            ),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
        }
        labels = {
            "minute_content": "Minute Content",
            "attachment": "Upload Attachment",
        }

    def clean(self):
        cleaned_data = super().clean()
        minute_content = cleaned_data.get("minute_content")
        attachment = cleaned_data.get("attachment")

        if not minute_content and not attachment:
            raise forms.ValidationError(
                "Please provide either minute content or an attachment."
            )
        if minute_content and attachment:
            raise forms.ValidationError(
                "You cannot provide both minute content and an attachment."
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
        fields = ["file", "attachment"] # Only allow selecting a file and uploading an attachment
        widgets = {
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
        }
        labels = {
            "attachment": "Upload Document",
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # Filter files that the current user has access to for association
        if self.user and self.user.is_authenticated:
            try:
                staff_user = Staff.objects.get(user=self.user)
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
