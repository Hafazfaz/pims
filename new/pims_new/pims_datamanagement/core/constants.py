from django.conf import settings

# Staff related constants
STAFF_TYPE_CHOICES = [
    ('permanent', 'Permanent'),
    ('locum', 'Locum'),
    ('contract', 'Contract'),
    ('nysc', 'NYSC'),
]

# File related constants
FILE_TYPE_CHOICES = [
    ("personal", "Personal"),
    ("policy", "Policy"),
]

STATUS_CHOICES = [
    ("inactive", "Inactive"),
    ("pending_activation", "Pending Activation"),
    ("active", "Active"),
    ("in_transit", "In Transit"),
    ("closed", "Closed"),
    ("archived", "Archived"),
]

# OTP constants
OTP_EXPIRY_MINUTES = 10

# Access request constants
ACCESS_REQUEST_DURATION_HOURS = 5

# PDF constants
DEFAULT_WATERMARK_TEXT = getattr(settings, 'DOCUMENT_WATERMARK_TEXT', "PIMS Confidential - Do Not Copy")
