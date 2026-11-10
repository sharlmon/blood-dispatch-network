# Africa's Talking SMS

The backend queues workflow notifications and inbound command replies in the same
SQLite transaction as the workflow change. A separate worker sends committed items;
HTTP handlers never call the external provider. SMS does not replace the phone
process, human crossmatching, release, or facility authorization.

## Configuration

Set these in private `backend/.env` for local development, or the deployment
EnvironmentFile. Existing live credentials can remain in place.

```dotenv
SMS_ENABLED=1
SMS_ENVIRONMENT=live
AFRICASTALKING_USERNAME=your_live_app_username
AFRICASTALKING_API_KEY=your_live_app_key
# Optional registered sender; omit to use the provider default.
AFRICASTALKING_SENDER_ID=
# A distinct, randomly generated secret of at least 32 characters.
AFRICASTALKING_CALLBACK_TOKEN=replace_with_random_callback_secret
# The registered receiving service/shortcode, not the recipient handset number.
AFRICASTALKING_INBOUND_NUMBERS=["your_shortcode"]
SMS_SENDERS={"+254700000001":{"user_id":"clerk_user_id","org_id":"clerk_org_id","facility_id":"HSP-004"}}
```

Only explicitly registered `SMS_SENDERS` receive workflow notifications or issue
commands. Do not guess facility/user mappings from test handset numbers. Map each
phone to its actual authorized user, organization and facility. Requester and
current supplier contacts receive lifecycle notifications, including confirmation
expiry and automatic selection of the next supplier. Replies suppress duplicate
notifications to the originating handset. Notification bodies contain a request
reference, event, state and attempt; no patient identifiers or blood group.

For sandbox, use `SMS_ENVIRONMENT=sandbox` and
`AFRICASTALKING_SANDBOX_API_KEY`; optionally set
`AFRICASTALKING_SANDBOX_SENDER_ID`. Username is automatically `sandbox`.
Live keys never fall back to sandbox or vice versa. Queue rows retain their
environment; switching the configuration does not send the other environment's
pending messages. SMS defaults to disabled, even when API keys are present.

Restart API processes after editing environment settings. Run from `backend/`:

```sh
.venv/bin/python -m flask --app wsgi sms-worker --once
.venv/bin/python -m flask --app wsgi sms-worker --interval 10
.venv/bin/python -m flask --app wsgi sms-status
```

For deployment, install `deploy/blood-sms.service` alongside the API and maintenance
services, adapting its paths/user to the host. Do not run a live worker against
test data unless intentionally sending to the registered recipients. Keep the
outbox database/backups private: they contain phone numbers and message bodies.

## Callbacks

Configure public HTTPS URLs in the Africa's Talking app's SMS callback settings:

- Incoming messages: `https://YOUR_BACKEND/api/sms/africastalking/inbound?token=CALLBACK_SECRET`
- Delivery reports: `https://YOUR_BACKEND/api/sms/africastalking/delivery?token=CALLBACK_SECRET`

This separate bearer token protects callbacks; it is not a provider signature.
Use HTTPS, redact query strings in reverse-proxy/access/error logs, and do not
publish the complete URLs. Flask's request logger records route templates only;
the provided Gunicorn configuration disables raw access logs. Do not use the
Flask development server with private callback URLs in a public deployment.
A localhost URL cannot receive external callbacks. Register the receiving
shortcode/service with the provider before enabling inbound traffic. An
alphanumeric sender ID alone does not provide two-way SMS. This adapter sends
bulk SMS replies; premium/on-demand linkId billing is not implemented.

Inbound callbacks accept form-encoded fields `id`, `from`, `to`, `text` (extra
provider metadata is ignored). Destination must be allowlisted; sender must be
registered. Commands are:

```text
REQUEST A+ 3
STATUS <request-id>
PICK <request-id> <supplier-id>
CONFIRM <request-id> <attempt> <units>
REJECT <request-id> <attempt> <reason>
DISPATCH <request-id> <attempt>
```

Authorization and workflow validation are identical to the signed gateway adapter.
Valid provider callbacks return HTTP 200, including duplicates. Message ID reuse
with a different command returns 409. Invalid/forbidden commands from registered
senders receive a generic queued error reply and HTTP 200, with no partial workflow
changes. Transient dependency errors return 503 so provider retries remain useful.
Unknown senders and invalid callback credentials never queue replies. The original
`POST /api/sms` HMAC envelope remains supported for other gateways; those gateways
send their own returned reply.

Delivery callbacks accept `id` (provider message ID) and `status`: `Success`,
`Failed`, `Rejected`, `Submitted`, `Buffered`. They update only the SMS outbox,
never the blood request. Reports arriving before the send response are retained
and applied when its provider ID becomes known. Duplicate and late pending
reports cannot regress a final state; `Success` takes precedence.

## Failures and operations

A successful HTTP send response is not sufficient: the worker checks the recipient
status code. Codes 100/101/102 with a message ID mean `accepted`, not `delivered`.
Only a delivery report with `Success` marks delivery. Recipient rejection 406
(`UserInBlacklist`) is `failed`, even if HTTP is 201. Provider 4xx responses are
also definite failures. Errors are stored as sanitized codes, never raw provider
payloads or credentials.

Network timeouts, invalid provider responses, provider 5xx, and claims abandoned
for five minutes become `unknown`. They are never automatically retried: the
provider may already have accepted the SMS. Inspect provider logs and use the
phone process to resolve uncertain notifications. Multiple workers claim queue
rows transactionally, preventing concurrent sends of the same item. Exactly-once
external delivery cannot be guaranteed across crashes; uncertainty is retained.

Use `sms-status` for counts. For a definite `failed` item, inspect the private
`sms_outbox` table's `id` and `error_code`, fix the cause, then explicitly requeue:

```sh
.venv/bin/python -m flask --app wsgi sms-retry <outbox-id>
```

This refuses accepted, delivered, delivery-failed and unknown items. Requeueing
can send a charged SMS once the worker runs. No workflow rollback occurs when
SMS sending fails. Outbox items/reports are retained for operator investigation;
plan a retention policy appropriate to your deployment before sustained use.

Provider references: [official Python SMS transport](https://github.com/AfricasTalkingLtd/africastalking-python/blob/develop/africastalking/SMS.py),
[callback configuration](https://help.africastalking.com/en/articles/2206161-how-do-i-configure-my-callback-url),
[incoming callback retry behavior](https://help.africastalking.com/en/articles/742510-where-are-my-incoming-messages).
