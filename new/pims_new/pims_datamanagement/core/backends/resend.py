import base64
import logging
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMultiAlternatives

logger = logging.getLogger(__name__)

class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, "RESEND_API_KEY", None)
        self.api_url = "https://api.resend.com/emails"

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        
        if not self.api_key:
            logger.error("RESEND_API_KEY is not configured in settings.")
            if not self.fail_silently:
                raise ValueError("RESEND_API_KEY is not configured in settings.")
            return 0

        num_sent = 0
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for message in email_messages:
            try:
                payload = self._prepare_payload(message)
                response = requests.post(self.api_url, json=payload, headers=headers)
                if response.status_code in [200, 201]:
                    num_sent += 1
                else:
                    logger.error(f"Failed to send email via Resend API: {response.status_code} - {response.text}")
                    if not self.fail_silently:
                        response.raise_for_status()
            except Exception as e:
                logger.error(f"Error sending email via Resend backend: {e}")
                if not self.fail_silently:
                    raise e
        return num_sent

    def _prepare_payload(self, message):
        from_email = message.from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        
        # Ensure 'to' is a list of strings
        to_emails = message.to
        if isinstance(to_emails, str):
            to_emails = [to_emails]

        payload = {
            "from": from_email,
            "to": to_emails,
            "subject": message.subject,
        }

        # Handle body (plain text / html)
        if isinstance(message, EmailMultiAlternatives):
            payload["text"] = message.body
            for content, mimetype in message.alternatives:
                if mimetype == "text/html":
                    payload["html"] = content
        else:
            if message.content_subtype == "html":
                payload["html"] = message.body
            else:
                payload["text"] = message.body

        if message.cc:
            payload["cc"] = message.cc if isinstance(message.cc, list) else [message.cc]
        if message.bcc:
            payload["bcc"] = message.bcc if isinstance(message.bcc, list) else [message.bcc]
        if message.reply_to:
            payload["reply_to"] = message.reply_to if isinstance(message.reply_to, list) else [message.reply_to]

        # Handle attachments
        if message.attachments:
            payload["attachments"] = []
            for attachment in message.attachments:
                # Django attachments can be:
                # 1. A tuple: (filename, content, mimetype)
                # 2. A MIMEBase object
                if isinstance(attachment, tuple):
                    filename, content, mimetype = attachment
                    if isinstance(content, str):
                        content_bytes = content.encode("utf-8")
                    else:
                        content_bytes = content
                    content_b64 = base64.b64encode(content_bytes).decode("utf-8")
                    payload["attachments"].append({
                        "filename": filename,
                        "content": content_b64,
                    })
                else:
                    try:
                        filename = attachment.get_filename()
                        content = attachment.get_payload(decode=True)
                        content_b64 = base64.b64encode(content).decode("utf-8")
                        payload["attachments"].append({
                            "filename": filename,
                            "content": content_b64,
                        })
                    except Exception as e:
                        logger.warning(f"Could not parse attachment: {attachment}. Error: {e}")

        return payload
