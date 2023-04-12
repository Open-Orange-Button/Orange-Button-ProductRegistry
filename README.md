# Orange Button Product Registry

## Installation

1. Use Python 3.10 or later and MySQL Server 8.0 or later.
1. Install the Python dependencies by running `pip3 install -r requirements.txt`.
1. In `product_registry/settings.py`, edit the path in `DATABASES['default']['OPTIONS']['read_default_file']` to point to your database credentials file (`.cnf`). A `.cnf` file contains:
   ```
   [client]
   host = <host_url>
   port = <MySQL_port>
   user = <username>
   password = <password>
   ```
1. Create a new database on the MySQL server with the command:
   ```
   CREATE DATABASE product_registry CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs;
   ```
1. Run `python3 manage.py makemigrations` and then `python3 manage.py migrate` to create the database tables.
