from django_otp.backends import OTPBackend
from django.contrib.auth.backends import ModelBackend

class CustomOTPBackend(OTPBackend, ModelBackend):
    pass
