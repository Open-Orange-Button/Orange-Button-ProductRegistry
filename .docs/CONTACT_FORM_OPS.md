# Contact Us / Feedback Form — Operations Guide

Operator-facing setup and maintenance for the public contact form at `/product/contact/`. Pairs with the developer-facing architecture notes in `CLAUDE.md` (see section "Contact / Feedback Form").

---

## Quick start checklist

After the feature is deployed, a one-time config pass is required:

- [ ] A Django superuser exists on prod
- [ ] `SiteSettings.feedback_email_to` is filled (recipient address)
- [ ] `SiteSettings.feedback_email_from` is a **verified** SES identity
- [ ] SES SMTP credentials are set in the ECS task definition env
- [ ] (Optional) `SiteSettings.webhook_url` is set to a Workato / Zapier / n8n / custom endpoint
- [ ] You've clicked **Send test webhook event** and seen a success banner

---

## 1. Creating / recovering a Django superuser

### 1a. Local dev
```bash
uv run python manage.py createsuperuser
```

### 1b. Production (no direct shell access to ECS tasks)

The service's ECS tasks do NOT have `enableExecuteCommand` on by default, so you can't `aws ecs execute-command` into them. Instead, run a one-off Fargate task against a special task definition that overrides the container's entrypoint.

**First time:** a task definition named `ob-product-registry-2026-02-superuser-oneoff` already exists in ECS (registered during the initial Contact Us deploy). Skip to the run-task step below.

**If it needs to be recreated:** copy the live task def, override entrypoint + command, register as a new family:

```bash
cd "/c/Work/BB/OB/OB Product registry"

MSYS_NO_PATHCONV=1 aws ecs describe-task-definition \
  --task-definition ob-product-registry-2026-02-app \
  --query 'taskDefinition' > taskdef.tmp.json

uv run python <<'PY'
import json
with open('taskdef.tmp.json') as f:
    td = json.load(f)
for k in ('taskDefinitionArn','revision','status','requiresAttributes',
         'compatibilities','registeredAt','registeredBy'):
    td.pop(k, None)
for c in td['containerDefinitions']:
    if c['name'] == 'ob-product-registry-2026-02-app':
        c['entryPoint'] = ['sh','-c']
        c['command'] = ['uv run python manage.py createsuperuser --noinput']
td['family'] = 'ob-product-registry-2026-02-superuser-oneoff'
with open('taskdef-oneoff.tmp.json','w') as f:
    json.dump(td, f)
PY

MSYS_NO_PATHCONV=1 aws ecs register-task-definition \
  --cli-input-json file://taskdef-oneoff.tmp.json

rm taskdef.tmp.json taskdef-oneoff.tmp.json
```

**Run the one-off task** (replace the password with a strong one):

```bash
MSYS_NO_PATHCONV=1 aws ecs run-task \
  --cluster ob-product-registry-2026-02-cluster \
  --task-definition ob-product-registry-2026-02-superuser-oneoff \
  --launch-type FARGATE \
  --network-configuration 'awsvpcConfiguration={subnets=[subnet-01fbf7e41805fd33e,subnet-0e417000e4bd14edc],securityGroups=[sg-0f82bfe30228d7318],assignPublicIp=DISABLED}' \
  --overrides '{"containerOverrides":[{"name":"ob-product-registry-2026-02-app","environment":[{"name":"DJANGO_SUPERUSER_USERNAME","value":"admin"},{"name":"DJANGO_SUPERUSER_EMAIL","value":"admin@oballiance.org"},{"name":"DJANGO_SUPERUSER_PASSWORD","value":"REPLACE_ME"}]}]}' \
  --query 'tasks[0].taskArn' --output text
```

Tail logs in CloudWatch log group `/ecs/ob-product-registry-2026-02-production` — look for `Superuser created successfully.` Task exits with code 0 on success.

> Generate a random password:
> `uv run python -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(24)))"`

---

## 2. Configuring destinations (Django admin)

Log in at `https://productregistry.oballiance.org/admin/` as the superuser.

Navigate to **Server → Site settings** (singleton; auto-redirects to the single instance's change page). Fields:

| Field | Purpose | Blank behavior |
|---|---|---|
| `feedback_email_to` | Comma-separated recipients | No email sent |
| `feedback_email_from` | SES-verified sender | Email skipped (required if `_to` is set) |
| `webhook_url` | HTTP endpoint for JSON POST | No webhook call |
| `rate_limit_per_hour` | Per-IP submission cap | `0` disables the rate limit |

The **Send test webhook event** button (top-right of the page) POSTs a synthetic `{"is_test": true, ...}` payload to the configured URL without creating a real submission. Use it to verify the downstream recipe before launch.

---

## 3. AWS SES setup (for the email path)

SES refuses to send mail claiming to be from an address you don't control. You prove control by verifying an **identity** — either a single email address or the whole domain.

### Option A — Verify a single email address (~2 min)

1. AWS Console → **Amazon SES** (region `us-east-1`) → **Identities** → **Create identity**
2. Type: **Email address**, value: e.g. `noreply@oballiance.org`
3. SES sends a verification link to that mailbox; click it
4. Once status shows ✅ verified, put the address in `SiteSettings.feedback_email_from`

### Option B — Verify the whole `oballiance.org` domain (recommended long-term)

1. AWS Console → **Amazon SES** → **Identities** → **Create identity**
2. Type: **Domain**, value: `oballiance.org`
3. SES produces DKIM CNAME records (and optionally SPF/DMARC suggestions)
4. Add them to the `oballiance.org` DNS zone (Route 53 / Cloudflare / wherever DNS lives)
5. Wait ~5–15 min for DKIM verification
6. Once verified, **any** `@oballiance.org` address works as `feedback_email_from`

### SES sandbox vs. production

New SES accounts start in **sandbox mode**: you can only send *to* verified addresses. For this feature:

- If `feedback_email_to` is a small, fixed list (e.g. `feedback@oballiance.org`), verify those recipients too and sandbox is fine.
- If you expect the recipient list to grow, request **production access** in the SES console (approval is usually same-day, sometimes immediate).

---

## 4. SES SMTP credentials + ECS env vars

Django's email backend (`django.core.mail.backends.smtp.EmailBackend`) talks to SES via SMTP. The settings are driven by env vars — see `product_registry/settings.py`. Without them, Django falls back to the **console backend** (emails "succeed" but are just printed to CloudWatch logs — webhook path still works).

### Create SMTP credentials

1. AWS Console → **Amazon SES** → **SMTP settings** → note the endpoint (`email-smtp.us-east-1.amazonaws.com`) and port (`587`)
2. Click **Create SMTP credentials**
3. SES creates a dedicated IAM user with send-only perms and gives you:
   - SMTP username (starts with `AKIA...`)
   - SMTP password (one-time download — save the CSV; it can't be retrieved later)

### Add env vars to the ECS task definition

Edit `ob-product-registry-2026-02-app` task def (Terraform or console). Add to the app container's `environment`:

| Env var | Value |
|---|---|
| `EMAIL_HOST` | `email-smtp.us-east-1.amazonaws.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | SMTP username from step 2 |
| `EMAIL_HOST_PASSWORD` | SMTP password from step 2 |
| `EMAIL_USE_TLS` | `1` |

**Security note:** The SMTP password is a secret. Don't commit it to Terraform plain-text. Use Terraform's `sensitive = true` and a `.tfvars` file that's gitignored, or AWS Secrets Manager with the task def's `secrets` block.

Force a new ECS deployment after editing the task def:

```bash
MSYS_NO_PATHCONV=1 aws ecs update-service \
  --cluster ob-product-registry-2026-02-cluster \
  --service ob-product-registry-2026-02-service \
  --force-new-deployment
```

---

## 5. End-to-end verification

After superuser + SES + SiteSettings are configured:

1. Open `https://productregistry.oballiance.org/product/` → see orange **Contact Us** button
2. Click it → submit a test message with a real email address
3. Lands on `/product/contact/thank-you/`
4. Check:
   - Django admin → Feedback submissions → row present
   - Recipient inbox → email arrived with the plain-text body
   - Row's `email_delivered_at` is non-null
5. If `webhook_url` is configured → row's `webhook_delivered_at` is non-null; downstream recipe (Workato / Zapier / etc.) received the payload

---

## 6. Troubleshooting

### Email submissions save but no email arrives
- Check the row's `delivery_notes` in admin — if it says `email failed: …`, the reason is there.
- Common causes:
  - `feedback_email_from` is not a verified SES identity → SES rejects the request
  - SES is in sandbox and `feedback_email_to` is not a verified recipient
  - `EMAIL_HOST_*` env vars are not set on the task → Django is using the console backend (emails go to CloudWatch)
- Check CloudWatch logs in `/ecs/ob-product-registry-2026-02-production` for `Feedback email delivery failed for submission …`

### Webhook `delivery_notes` say `webhook failed: HTTP 403` (or similar)
- The URL is reachable but the destination rejected the payload. Usually auth — verify the recipe is actually listening on that URL and accepting JSON POST.

### Webhook says `webhook failed: timeout`
- Hit the 10-second timeout. The destination is either slow or unreachable (firewall / VPC egress rules).

### Rate-limit tripping unexpectedly
- Check `SiteSettings.rate_limit_per_hour`. If users behind a shared NAT are hitting it, increase or set to 0 to disable.
- Remember: the limit is per source IP, counted over the last hour of rows in `FeedbackSubmission`.

### Honeypot catching real users
- Shouldn't happen — the `website` field is hidden via CSS. If a user reports it happening, inspect their user-agent in CloudWatch INFO logs (`contact honeypot tripped ip=… user_agent=…`) and check whether some accessibility tool fills hidden fields.

### Log snippets to grep for in CloudWatch

| Event | Log pattern |
|---|---|
| Submission saved | `contact submission saved id=` |
| Honeypot trip | `contact honeypot tripped ip=` |
| Rate-limit trip | `contact rate-limit tripped ip=` |
| Email failure | `Feedback email delivery failed for submission` |
| Webhook failure | `Webhook call failed for submission` or `Webhook returned` |

---

## 7. Data retention (not implemented yet)

`FeedbackSubmission` rows currently persist forever. If compliance requires pruning, a Django management command or a scheduled ECS task running `FeedbackSubmission.objects.filter(created_at__lt=…).delete()` would do it. See the "Open questions" section of the design spec (`docs/superpowers/specs/2026-04-20-contact-us-form-design.md`).
