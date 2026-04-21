# OB Product Registry

## Project Overview
Django-based product registry for Orange Button (OB) solar/renewable energy equipment.
Server-side rendered (Django templates + Bootstrap 5), no JS frontend framework, no DRF.

## Tech Stack
- **Python 3.14**, Django 6, Gunicorn
- **Package manager**: uv (pyproject.toml, uv.lock)
- **Local DB**: SQLite (`db.sqlite3`)
- **Production DB**: MySQL 8.4 on AWS RDS (private VPC)
- **Infrastructure**: Terraform (AWS ECS Fargate, RDS, ECR, ALB, bastion)
- **Templates**: Django templates in `server/templates/server/`
- **Static**: CSS/images only, no JS build step

## Project Structure
```
server/                  # Main Django app
  models.py              # All product/entity models (~960 lines)
  views.py               # Views + model_to_ob_json() serialization
  urls.py                # URL routes (app_name='product')
  templates/server/      # Django templates
  data_upsert/           # Jupyter notebooks + CSVs for data loading
    upsert_utils.py      # DuckDB-based insert helper (insert_recursive)
    ProdBattery/          # Battery data cleaning + upsert notebooks
    ProdModule/           # Module data cleaning + upsert notebooks
    upsert_sourcecountry_no_orm.ipynb
ob_taxonomy/             # OB taxonomy metadata app
  models.py              # OBObject, OBElement, OBItemType, etc.
product_registry/        # Django project config
  settings.py            # Settings (SQLite local, MySQL via env vars in prod)
  urls.py                # Root URL config
terraform/               # AWS infrastructure
  database.tf            # RDS MySQL instance
  ecs_service.tf         # ECS Fargate service (2 replicas)
  bastion.tf             # Bastion host for SSH tunnel to RDS
  ecr.tf                 # Container registry
load_local_db_to_remote_db.sql  # DuckDB script: SQLite -> RDS data transfer
start.sh                 # Container entrypoint: migrate + collectstatic + gunicorn
Dockerfile               # uv-based container image
```

## Key Architecture Decisions

### Serialization
No DRF serializers. Single function `model_to_ob_json()` in `views.py` handles all
serialization by walking the OB taxonomy (`ob_taxonomy.OBObject`) to discover fields
and relationships dynamically. Outputs grouped dict: elements, nested_objects,
element_arrays, object_arrays.

### Product Inheritance
`Product` is the base model. Subclasses: `ProdBattery`, `ProdCell`, `ProdModule`.
`determine_product_subclass()` resolves base Product to concrete subclass via
reverse OneToOne relations.

### Data Loading Pipeline
1. Jupyter notebooks clean CSV data and insert into local SQLite (bypassing ORM, using DuckDB)
2. `load_local_db_to_remote_db.sql` transfers from SQLite to RDS via SSH tunnel through bastion
3. On ECS container startup, `start.sh` runs `migrate --noinput`

### Field Naming Convention
All model fields follow `FieldName_Value` and `FieldName_Unit` pattern.
Enums use Django TextChoices: `{ItemTypeName}Enum`, `{ItemTypeName}Unit`.

### Contact / Feedback Form
Public form linked from the "Contact Us" button in the navbar (every page).

**Code layout:**
- `server/feedback.py` — `ContactForm` + `send_feedback_email()` + `post_to_workato()` (stdlib `urllib.request`, no new deps)
- `server/views.py` — `contact` + `contact_thank_you` views; helpers `_client_ip` (validates XFF, falls back to `REMOTE_ADDR`), `_mask_email`, `_rate_limit_exceeded`
- `server/models.py` — `FeedbackSubmission` (every submission saved) + `SiteSettings` (singleton, `pk=1`, destination config)
- Templates: `contact.html`, `contact_thank_you.html`; button in `base.html`

**Flow:** POST → validate → honeypot check → rate-limit check → save row → best-effort email + Workato webhook → 302 to thank-you. DB row is canonical; delivery failures are logged in `delivery_notes` but never surface to the user.

**Configuring destinations** — Django admin → "Site settings" (singleton, auto-redirects to `pk=1`):
- `feedback_email_to` — comma-separated recipients (blank = no email)
- `feedback_email_from` — must be verified in SES for prod
- `workato_webhook_url` — Workato recipe webhook URL (blank = no webhook)
- `rate_limit_per_hour` — default 3, `0` disables

**Reviewing submissions** — Django admin → "Feedback submissions" (read-only). `email_delivered_at` / `webhook_delivered_at` show per-destination success; `delivery_notes` holds failure reasons.

**Spam protection:** hidden honeypot (`website` field) silently drops bot submissions; per-IP rate limit backed by DB.

**Email backend (env-driven, `product_registry/settings.py`):**
- No `EMAIL_HOST` env var → console backend (local dev; emails print to runserver terminal)
- `EMAIL_HOST` set → SMTP (AWS SES SMTP in prod)
- Env vars: `EMAIL_HOST`, `EMAIL_PORT` (default 587), `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` (default `1`)

**Superuser creation** (one-off, required for admin access):
```bash
# Local:
uv run python manage.py createsuperuser
# Non-interactive (good for prod via ECS exec/bastion):
DJANGO_SUPERUSER_USERNAME=admin DJANGO_SUPERUSER_EMAIL=ops@example.com \
DJANGO_SUPERUSER_PASSWORD=... uv run python manage.py createsuperuser --noinput
```

**Data reload caveat:** `load_local_db_to_remote_db.sql` explicitly excludes `server_feedbacksubmission` and `server_sitesettings` — both are prod-only, copying from local would wipe production config/submissions.

**Tests:** `server/tests.py` — Django `TestCase`s. Run with `uv run python manage.py test server`.

## URL Routes
| Route | View | Description |
|-------|------|-------------|
| `/product/` | `product_list` | Searchable product list |
| `/product/us-domestic-content/` | `product_list_us_domestic` | US domestic content table |
| `/product/contact/` | `contact` | Public contact / feedback form |
| `/product/contact/thank-you/` | `contact_thank_you` | Form submission confirmation |
| `/product/<uuid>/` | `product_detail_by_ProdID` | Product detail page |
| `/product/<uuid>/json` | `product_json` | JSON export (file download) |
| `/product/<slug>/` | `product_detail_by_ProdCode` | Redirect to detail by code |
| `/admin/` | Django admin | Site settings + feedback submissions |

## Running Locally
```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

## Deployment
```bash
# Build and push Docker image to ECR, then update ECS service
# Migrations run automatically on container startup via start.sh
```

## Data Reload (wipe and reload)
When schema changes require a full data reload:
1. Delete local `db.sqlite3`
2. `uv run python manage.py migrate` (recreate empty schema)
3. Run taxonomy upload notebook: `ob_taxonomy/upload_taxonomy.ipynb`
4. Run data upsert notebooks in `server/data_upsert/`
5. SSH tunnel to RDS via bastion, then run `load_local_db_to_remote_db.sql`
   - Update the SQL script if table names changed

## Important Notes
- `terraform/terraform.tfvars` is gitignored (contains DB passwords)
- Django admin (`server/admin.py`) registers `FeedbackSubmission` (read-only) and `SiteSettings` (singleton); product models are not in admin
- No CI/CD pipeline — Docker build and deploy is manual
- The `upsert_utils.py` helper uses DuckDB for bulk inserts (bypasses Django ORM)
- Design docs for new features live under `docs/superpowers/specs/` and plans under `docs/superpowers/plans/`
