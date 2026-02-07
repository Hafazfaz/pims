from django import forms
from organization.models import StaffSignature

class SignatureUploadForm(forms.ModelForm):
    class Meta:
        model = StaffSignature
        fields = ['image']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'block w-full text-sm text-slate-500 file:mr-4 file:py-3 file:px-6 file:rounded-xl file:border-0 file:text-[10px] file:font-black file:uppercase file:tracking-widest file:bg-slate-900 file:text-white hover:file:bg-black transition-all cursor-pointer',
                'accept': 'image/*'
            })
        }
