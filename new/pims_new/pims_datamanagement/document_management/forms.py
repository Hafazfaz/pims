from django import forms
from .models import File, Department, Document
from user_management.models import CustomUser # Import CustomUser

class FileForm(forms.ModelForm):
    class Meta:
        model = File
        fields = ['title', 'file_type', 'department', 'owner']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter file title (e.g., PERSONNEL FILE OF JOHN DOE)'}),
            'file_type': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'owner': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'title': 'File Title',
            'file_type': 'File Type',
            'department': 'Department (for Policy Files)',
            'owner': 'File Owner',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make department optional for personal files
        if self.initial.get('file_type') == 'personal':
            self.fields['department'].required = False
        
        # Filter departments if needed, or add a default empty choice
        self.fields['department'].queryset = Department.objects.all().order_by('name')
        self.fields['department'].empty_label = "Select Department (Optional for Personal Files)"

    def clean_title(self):
        title = self.cleaned_data['title']
        return title.upper() # Enforce uppercase for title

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['minute_content', 'attachment']
        widgets = {
            'minute_content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter minute content...'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'minute_content': 'Minute Content',
            'attachment': 'Upload Attachment',
        }

    def clean(self):
        cleaned_data = super().clean()
        minute_content = cleaned_data.get('minute_content')
        attachment = cleaned_data.get('attachment')

        if not minute_content and not attachment:
            raise forms.ValidationError("Please provide either minute content or an attachment.")
        if minute_content and attachment:
            raise forms.ValidationError("You cannot provide both minute content and an attachment.")
        
        return cleaned_data

class SendFileForm(forms.Form):
    recipient = forms.ModelChoiceField(
        queryset=CustomUser.objects.all().order_by('username'),
        empty_label="Select Recipient",
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Send to"
    )
