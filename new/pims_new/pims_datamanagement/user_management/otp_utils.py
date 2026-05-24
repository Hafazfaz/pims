# This file is now a wrapper around core.utils.otp for backward compatibility.
# In the future, callers should import directly from core.utils.otp.

from core.utils.otp import (  # noqa: F401
    clear_otp_session,
    generate_otp,
    send_otp_email,
    set_otp_in_session,
    verify_otp_in_session,
)
