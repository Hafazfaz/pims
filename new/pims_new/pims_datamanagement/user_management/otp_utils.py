import secrets
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta, datetime

def generate_otp():
    """Generates a random 6-digit OTP."""
    return "".join(secrets.choice("0123456789") for _ in range(6))

def send_otp_email(user, otp):
    """Sends the OTP to the user's email address."""
    subject = "Your PIMS Login OTP"
    message = f"Hello {user.get_full_name() or user.username},\n\nYour One-Time Password (OTP) for PIMS login is: {otp}\n\nThis OTP is valid for 10 minutes.\n\nIf you did not request this, please ignore this email."
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user.email]
    
    send_mail(subject, message, from_email, recipient_list)

def set_otp_in_session(request, user_id, otp):
    """Stores the OTP and its metadata in the session."""
    request.session['pending_otp_user_id'] = user_id
    request.session['pending_otp_code'] = otp
    request.session['pending_otp_expiry'] = (timezone.now() + timedelta(minutes=10)).isoformat()

def verify_otp_in_session(request, otp_input):
    """Verifies the input OTP against the one stored in the session."""
    stored_otp = request.session.get('pending_otp_code')
    expiry_str = request.session.get('pending_otp_expiry')
    user_id = request.session.get('pending_otp_user_id')

    if not stored_otp or not expiry_str or not user_id:
        return None, "No active OTP session found."

    expiry = datetime.fromisoformat(expiry_str)
    if timezone.now() > expiry:
        # Clear session
        clear_otp_session(request)
        return None, "OTP has expired. Please log in again."

    if stored_otp != otp_input:
        return None, "Invalid OTP. Please try again."

    # Success
    return user_id, None

def clear_otp_session(request):
    """Clears OTP related data from the session."""
    request.session.pop('pending_otp_user_id', None)
    request.session.pop('pending_otp_code', None)
    request.session.pop('pending_otp_expiry', None)
