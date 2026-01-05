from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.urls import reverse
from user_management.models import CustomUser
from notifications.utils import create_notification # Import notification utility

class Command(BaseCommand):
    help = 'Sends email warnings to users whose passwords are about to expire.'

    def handle(self, *args, **kwargs):
        # Determine the expiry threshold
        warning_threshold = timezone.now() + timedelta(days=settings.PASSWORD_EXPIRY_WARNING_DAYS)
        password_expiry_days = getattr(settings, 'PASSWORD_EXPIRY_DAYS', 90) # Default to 90 if not set in middleware

        users_to_warn = CustomUser.objects.filter(
            is_active=True,
            must_change_password=False, # Don't warn if already forced to change
            last_password_change__isnull=False,
            last_password_change__lte=timezone.now() - timedelta(days=password_expiry_days - settings.PASSWORD_EXPIRY_WARNING_DAYS)
        )

        site_name = getattr(settings, 'SITE_NAME', 'PIMS') # Default site name

        for user in users_to_warn:
            expiry_date = user.last_password_change + timedelta(days=password_expiry_days)
            days_until_expiry = (expiry_date - timezone.now()).days

            if days_until_expiry > 0: # Only send if still some days left before actual expiry
                password_change_url = self.build_password_change_url(user)
                
                context = {
                    'user': user,
                    'site_name': site_name,
                    'days_until_expiry': days_until_expiry,
                    'password_change_url': password_change_url,
                }
                
                email_subject_template = render_to_string('emails/password_expiry_warning.txt', context).split('\n')[0].replace('Subject: ', '')
                email_body = render_to_string('emails/password_expiry_warning.txt', context)

                send_mail(
                    email_subject_template,
                    email_body,
                    settings.DEFAULT_FROM_EMAIL, # Ensure this is set in settings
                    [user.email],
                    fail_silently=False,
                )
                # Create in-app notification
                create_notification(
                    user=user,
                    message=f"Your password will expire in {days_until_expiry} days. Please change it soon.",
                    link=password_change_url
                )
                self.stdout.write(self.style.SUCCESS(f"Sent password expiry warning to {user.email}. Password expires in {days_until_expiry} days."))
            else:
                 self.stdout.write(self.style.WARNING(f"Skipped sending warning to {user.email} as password has already expired or expires today."))


    def build_password_change_url(self, user):
        # This assumes a specific URL pattern for password change
        # Adjust 'user_management:password_change_force' if your URL is different
        return settings.BASE_URL + reverse('user_management:password_change_force')
