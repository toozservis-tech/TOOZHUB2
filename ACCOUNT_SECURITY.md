# Account flow security, 2026-09-28

Implemented and tested:
- Normalized user registration creates an isolated tenant and cannot assign administrator privileges from request fields.
- Service registration requires an administrator decision. Approval locks the request to prevent double consumption.
- New registration/reset/change passwords require at least 12 characters, reject trivial values and reject more than bcrypt's 72 UTF-8 bytes. Existing short passwords may still log in; no recovered account was silently reset.
- Independent per-IP and per-account throttles cover authentication and recovery; the in-process limiter is thread-safe with bounded key storage.
- Reset links contain an opaque 256-bit token in the URL fragment, not in access logs. Only SHA-256 digests are stored, expire after 30 minutes, are locked and consumed once. Deleted/suspended accounts cannot reset.
- Password changes revoke existing sessions and pending two-factor challenges. Reset links are cleared. The iOS app returns to login after changing its password.
- Missing email configuration returns a global 503, never an invented delivery success or a reset URL. Existing/nonexistent account requests have the same response body when delivery is configured. Provider failures are kept private and revoke the undelivered token.
- Cloud diagnostics returning database credentials are disabled in production. Local diagnostics redact the database password.
- Sensitive API/reset-page responses use no-store. JWT requires signed expiry, issue time and subject. Missing bcrypt fails closed for new hashes.
- Resend HTTPS email transport is available through RESEND_API_KEY and EMAIL_FROM. SMTP remains supported with certificate validation for hosts allowing SMTP ports.

Validation:
- Isolated unittest suite: `python -m unittest discover -s tests/security -v` (no real email/database).
- Real PostgreSQL and public HTTPS user registration, service request, denied pre-approval login, admin approval, successful service login, denied ordinary-user admin access and denied unrelated photo access.
- Synthetic cloud test accounts suspended after verification, retained for audit.
- Updated physical iPhone build/install succeeded.

Still required before calling this production-ready:
- Configure a verified email sender/provider and test actual inbox delivery and browser reset end-to-end. No provider key is currently configured. Email ownership verification is not yet enforced for user registration.
- The database password was rotated through Supabase on 2026-09-28 and Render was updated. The old diagnostic route is closed; historical access has not been ruled out. Keep this incident in the security review.
- The limiter and 2FA challenges are per-process and reset on restart. Shared persistent throttling is required before horizontal scaling; this does not claim DDoS protection.
- Full application-wide authorization/dependency audit, mandatory administrator MFA enrollment, and a tested scheduled database backup/restore policy remain separate work. This is not certification of the entire legacy application.

Never place SMTP/API/database credentials in Git, the iOS bundle, browser storage, or reports.
