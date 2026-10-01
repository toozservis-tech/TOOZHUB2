"""Browser defenses shared by the admin sign-in and dashboard, with no config IO."""

ADMIN_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; script-src-attr 'none'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-src 'none'; frame-ancestors 'none';"
)

# The compatibility dashboard previews authenticated attachments in an inert blob
# frame. Scripts remain external and no third-party resource receives admin data.
LEGACY_ADMIN_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; script-src-attr 'none'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-src blob:; frame-ancestors 'none';"
)
