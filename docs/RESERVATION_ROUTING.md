# Reservation account routing

Selectable service recipients must have the `service` role and an active,
nondeleted account. The shared predicate is used by service directories,
customer contacts, invitation acceptance and reservation creation. Administrators
retain global oversight through the existing authenticated admin routes, but
are never silently used as service recipients.

The numeric service account ID selected by the customer is stored unchanged.
Creation mail resolves that ID against the current database and verifies the
role again before delivering. It does not resolve recipients by display name,
copy the administrator, or fall back to an administrator address. Legacy
reservations assigned to a nonservice account are not mailed until corrected.

A customer can reserve their own vehicle. A service can reserve only for itself
and only with current approved access to that vehicle. A booking does not create
vehicle history grants, contact consent or legacy automatic invitations. Those
permissions remain in the separate explicit customer approval workflow.
Service visibility is scoped to its own reservations; both admin roles retain
the overall reservation view. Existing admin MFA enforcement remains unchanged.

Service directory tenant restrictions are preserved, including explicit active
customer contacts across tenants. Disabled/deleted service accounts and legacy
admin contacts are omitted. Unrelated foreign tenant accounts stay hidden.

Mail links to `/web/reservations.html`, a public page containing no reservation
or authentication data. The iOS `spravavozidel://reservations` route opens the
reservation tab without logging out or changing the current account. The
selection form shows the service email alongside its name to distinguish names.

Verification: synthetic SQLite relationships, isolated PostgreSQL HTTP flows,
fake mail transport and existing web authorization/consent regressions. These
tests do not send real mail, create production test accounts or make payments.
