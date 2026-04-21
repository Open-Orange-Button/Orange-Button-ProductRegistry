# Data Loading Guide

How to load enrichment data (CEC references, datasheet URLs, domestic content attestations, etc.) from spreadsheets into the OB Product Registry.

## Overview

There are two types of data loads:

1. **Full load** (rare) - wipe local DB, rebuild from scratch via Jupyter notebooks, push everything to prod via DuckDB
2. **Enrichment update** (common) - update existing products with new field values from a spreadsheet

This guide covers both, with emphasis on enrichment updates since those are the most frequent operation.

---

## Prerequisites

- AWS CLI configured (`aws sts get-caller-identity` should work)
- Python dependencies installed (`uv sync`)
- SSH key pair at `terraform/bastion_key` and `terraform/bastion_key.pub`
- Docker Desktop (only needed if deploying schema changes)
- Terraform installed (only needed for bastion creation)

### Key infrastructure details

| Resource | Value |
|----------|-------|
| RDS host | `ob-product-registry-2026-02-db-instance.cnw22meaiwwb.us-east-1.rds.amazonaws.com` |
| RDS security group | `sg-0a12556b7c71cfc60` |
| DB name | `OBProductRegistry` |
| DB user | `admin` |
| DB password | see `terraform/terraform.tfvars` |
| Local tunnel port | `3307` -> RDS `3306` |
| ECS cluster | `ob-product-registry-2026-02-cluster` |
| ECS service | `ob-product-registry-2026-02-service` |
| Prod URL | https://productregistry.oballiance.org/product/ |

---

## Enrichment Update (common case)

Use this when you have a spreadsheet with new data for existing products (e.g., CEC references, datasheet URLs, domestic content attestations).

### Step 1: Backup local database

```bash
cp db.sqlite3 "db.sqlite3.backup-$(date +%Y-%m-%d)"
```

### Step 2: Load data into local SQLite

Use Django ORM to match products by `ProdCode_Value` and update fields.

```python
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'product_registry.settings')

import django
django.setup()

import openpyxl
from server.models import Product, SourceCountry

wb = openpyxl.load_workbook('.tmp/your_spreadsheet.xlsx')
ws = wb['SheetName']
headers = [cell.value for cell in ws[1]]

for row in ws.iter_rows(min_row=2, values_only=True):
    data = dict(zip(headers, row))
    code = data['Registry ProdCode']

    try:
        product = Product.objects.get(ProdCode_Value=code)
    except Product.DoesNotExist:
        print(f'NOT FOUND: {code}')
        continue

    # Update CEC reference
    cec_ref = data.get('CEC Reference / Model') or ''
    if cec_ref and not product.CECProdCode_Value:
        product.CECProdCode_Value = cec_ref

    # Update datasheet URL
    datasheet = data.get('Datasheet URL') or ''
    if datasheet and not product.ProdDatasheetURL_Value:
        product.ProdDatasheetURL_Value = datasheet

    product.save()

    # Create SourceCountry if attestation URL exists
    attestation_url = data.get('Domestic Content Attestation URL') or ''
    if attestation_url and attestation_url.startswith('http'):
        if not SourceCountry.objects.filter(Product=product, CountryOfManufacture_Value='US').exists():
            SourceCountry.objects.create(
                Product=product,
                CountryOfManufacture_Value='US',
                AttestationURL_Value=attestation_url,
            )
```

### Step 3: Verify locally

```bash
uv run python manage.py runserver
```

Check product detail pages at `http://localhost:8000/product/<ProdCode>/` to confirm data appears correctly.

### Step 4: Create RDS snapshot (production backup)

```bash
aws rds create-db-snapshot \
  --db-instance-identifier ob-product-registry-2026-02-db-instance \
  --db-snapshot-identifier ob-product-registry-<description>-<date>
```

Check progress (optional, don't need to wait):
```bash
aws rds describe-db-snapshots \
  --db-snapshot-identifier ob-product-registry-<description>-<date> \
  --query 'DBSnapshots[0].{Status:Status,Progress:PercentProgress}' --output table
```

### Step 5: Update bastion IP and create bastion

Check your current IP:
```bash
curl -s https://checkip.amazonaws.com
```

If your IP changed, update `cidr_blocks` in `terraform/bastion.tf`, then:
```bash
cd terraform
terraform apply \
  -target=aws_security_group.bastion_sg \
  -target=aws_key_pair.bastion_key \
  -target=aws_instance.bastion \
  -auto-approve
```

Note the `bastion_public_ip` from the output.

### Step 6: Allow bastion to access RDS

```bash
aws ec2 authorize-security-group-ingress \
  --group-id sg-0a12556b7c71cfc60 \
  --protocol tcp --port 3306 \
  --source-group <bastion-sg-id-from-terraform-output>
```

### Step 7: Open SSH tunnel

```bash
ssh -i terraform/bastion_key \
  -o StrictHostKeyChecking=no \
  -o ServerAliveInterval=30 \
  -f -N \
  -L 3307:ob-product-registry-2026-02-db-instance.cnw22meaiwwb.us-east-1.rds.amazonaws.com:3306 \
  ec2-user@<bastion-ip>
```

### Step 8: Dry run - compare local vs prod

```python
import MySQLdb
import sqlite3

prod = MySQLdb.connect(
    host='127.0.0.1', port=3307, user='admin',
    passwd='<see terraform/terraform.tfvars>',
    db='OBProductRegistry', autocommit=False, charset='utf8mb4'
)
pc = prod.cursor()

local = sqlite3.connect('db.sqlite3')
lc = local.cursor()

codes = ['PROD-CODE-1', 'PROD-CODE-2']  # your product codes

for code in codes:
    lc.execute(
        'SELECT CECProdCode_Value, ProdDatasheetURL_Value FROM server_product WHERE ProdCode_Value = ?',
        (code,)
    )
    local_cec, local_ds = lc.fetchone()

    pc.execute(
        'SELECT CECProdCode_Value, ProdDatasheetURL_Value FROM server_product WHERE ProdCode_Value = %s',
        (code,)
    )
    prod_cec, prod_ds = pc.fetchone()

    print(f'{code}:')
    print(f'  CEC:  prod={prod_cec!r}  local={local_cec!r}  {"CHANGE" if local_cec != prod_cec else "same"}')
    print(f'  DS:   prod={prod_ds!r}  local={local_ds!r}  {"CHANGE" if local_ds != prod_ds else "same"}')

prod.close()
local.close()
```

### Step 9: Push to production

```python
import MySQLdb
import sqlite3

prod = MySQLdb.connect(
    host='127.0.0.1', port=3307, user='admin',
    passwd='<see terraform/terraform.tfvars>',
    db='OBProductRegistry', autocommit=False, charset='utf8mb4'
)
pc = prod.cursor()

local = sqlite3.connect('db.sqlite3')
lc = local.cursor()

codes = ['PROD-CODE-1', 'PROD-CODE-2']  # your product codes

for code in codes:
    lc.execute(
        'SELECT CECProdCode_Value, ProdDatasheetURL_Value FROM server_product WHERE ProdCode_Value = ?',
        (code,)
    )
    local_cec, local_ds = lc.fetchone()

    pc.execute(
        'UPDATE server_product SET CECProdCode_Value = %s, ProdDatasheetURL_Value = %s WHERE ProdCode_Value = %s',
        (local_cec, local_ds, code)
    )
    print(f'Updated {code} (rows affected: {pc.rowcount})')

# Verify before commit
pc.execute(
    'SELECT ProdCode_Value, CECProdCode_Value, ProdDatasheetURL_Value FROM server_product WHERE ProdCode_Value IN (%s)' % ','.join(['%s'] * len(codes)),
    codes
)
for row in pc.fetchall():
    print(f'  {row[0]}: CEC={row[1]!r}, DS={row[2]!r}')

prod.commit()
print('Committed!')

prod.close()
local.close()
```

For SourceCountry records (domestic content attestations), also push those:
```python
# After the product updates, if you created SourceCountry records locally:
lc.execute('''
    SELECT sc.id, sc.CountryOfManufacture_Value, sc.AttestationURL_Value,
           sc.AssignedCostPercentage_Value, sc.AssignedCostPercentage_Unit,
           p.ProdCode_Value
    FROM server_sourcecountry sc
    JOIN server_product p ON sc.Product_id = p.id
    WHERE p.ProdCode_Value IN (...)
''')
for row in lc.fetchall():
    # Get prod product ID
    pc.execute('SELECT id FROM server_product WHERE ProdCode_Value = %s', (row[5],))
    prod_product_id = pc.fetchone()[0]
    pc.execute('''
        INSERT INTO server_sourcecountry
        (CountryOfManufacture_Value, AttestationURL_Value, AssignedCostPercentage_Value,
         AssignedCostPercentage_Unit, Product_id, CountryOfManufactureIsNotPFE_Value,
         CountryOfOwnershipForPFE_Value, CountryOfOwnershipIsNotPFE_Value)
        VALUES (%s, %s, %s, %s, %s, NULL, '', NULL)
    ''', (row[1], row[2], row[3], row[4], prod_product_id))
```

### Step 10: Verify on production

Check product detail pages at `https://productregistry.oballiance.org/product/<ProdCode>/`.

Quick verification via curl:
```bash
curl -sL "https://productregistry.oballiance.org/product/<PROD_CODE>/" | grep -A1 "ProdDatasheetURL"
```

### Step 11: Cleanup

Revoke bastion access to RDS:
```bash
aws ec2 revoke-security-group-ingress \
  --group-id sg-0a12556b7c71cfc60 \
  --protocol tcp --port 3306 \
  --source-group <bastion-sg-id>
```

Destroy bastion:
```bash
cd terraform
terraform destroy \
  -target=aws_instance.bastion \
  -target=aws_key_pair.bastion_key \
  -target=aws_security_group.bastion_sg \
  -auto-approve
```

---

## Full Load (rebuild from scratch)

Use this when schema changes require a complete data reload, or when setting up the database for the first time.

### Step 1: Rebuild local database

```bash
rm db.sqlite3
uv run python manage.py migrate
```

### Step 2: Load OB taxonomy

Run the notebook `ob_taxonomy/upload_taxonomy.ipynb` (requires `jq` installed).

### Step 3: Clean and upsert CEC data

For each product type, run the clean notebook then the upsert notebook:

```
server/data_upsert/ProdBattery/clean.ipynb    -> then -> upsert_no_orm.ipynb
server/data_upsert/ProdModule/clean.ipynb      -> then -> upsert_no_orm.ipynb
```

These use DuckDB to bulk-insert into SQLite, bypassing the Django ORM.

### Step 4: Deploy (if schema changed)

If Django models changed, migrations need to run on production:
```bash
uv run python manage.py makemigrations server
uv run python manage.py migrate  # local

# Build and deploy new Docker image
bash deploy.sh
```

Migrations run automatically on ECS container startup via `start.sh`.

### Step 5: Push data to production

Follow Steps 4-11 from the Enrichment Update section above.

For a full load, you can use `load_local_db_to_remote_db.sql` with DuckDB instead of the Python approach:

```bash
# With SSH tunnel open on port 3307:
duckdb
```

```sql
ATTACH 'db.sqlite3' AS lds (TYPE sqlite);
ATTACH 'host=localhost user=admin password=<PASSWORD> database=OBProductRegistry port=3307' AS rds (TYPE mysql);

BEGIN TRANSACTION;
-- See load_local_db_to_remote_db.sql for the full list of INSERT statements
-- IMPORTANT: verify counts before committing
COMMIT;
```

---

## Common product fields for enrichment

| Spreadsheet Column | Django Model Field | Notes |
|---|---|---|
| CEC Reference / Model | `Product.CECProdCode_Value` | Internal reference, not shown in OB taxonomy serialization |
| Datasheet URL | `Product.ProdDatasheetURL_Value` | Shown on product detail page |
| UPC / SKU | `Product.ManufacturerUPC_Value` | |
| Domestic Content Attestation URL | `SourceCountry.AttestationURL_Value` | Create a SourceCountry record with `CountryOfManufacture_Value='US'` |
| Assigned Cost Percentage | `SourceCountry.AssignedCostPercentage_Value` | Float, paired with `_Unit` |

Products are always matched by `ProdCode_Value` (the Registry ProdCode column in spreadsheets).

---

## Rollback

### Local
```bash
cp db.sqlite3.backup-<date> db.sqlite3
```

### Production (restore from RDS snapshot)
```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier ob-product-registry-2026-02-db-instance-restored \
  --db-snapshot-identifier <snapshot-id>
```
Then update ECS task definition to point to the new DB hostname.

### Docker image rollback
```bash
docker pull 545009828484.dkr.ecr.us-east-1.amazonaws.com/ob-product-registry-2026-02-repo:pre-<tag>
docker tag ...:pre-<tag> ...:latest
docker push ...:latest
aws ecs update-service --cluster ob-product-registry-2026-02-cluster \
  --service ob-product-registry-2026-02-service --force-new-deployment
```
