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

## URL Routes
| Route | View | Description |
|-------|------|-------------|
| `/product/` | `product_list` | Searchable product list |
| `/product/domestic-content/` | `domestic_content` | US domestic content table |
| `/product/<uuid>/` | `product_detail_by_ProdID` | Product detail page |
| `/product/<uuid>/json` | `product_json` | JSON export (file download) |
| `/product/<slug>/` | `product_detail_by_ProdCode` | Redirect to detail by code |

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
- `admin.py` is empty — no models registered in Django admin
- No CI/CD pipeline — Docker build and deploy is manual
- The `upsert_utils.py` helper uses DuckDB for bulk inserts (bypasses Django ORM)
