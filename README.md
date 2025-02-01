# Orange Button Product Registry

### Development Environment Setup

**These are not instructions for deploying this project into production. Refer to the Django documentation for those.**

The following steps set up the Ubuntu Linux environment for this project.
For developers without Ubuntu Linux, see the next section for instructions to set up this project in a Docker container.

1. Use Python 3.10 and MySQL Server 8.
1. Install `libmysqlclient`.
   ```
   sudo apt install libmysqlclient-dev
   ```
1. Create a Python virtual environment and activate it.
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```
1. Install the Python dependencies by running `pip3 install -r requirements.txt`.
1. In `product_registry/settings.py`, edit the path in `DATABASES['default']['OPTIONS']['read_default_file']` to point to your database credentials file (`.cnf`). A `.cnf` file contains:
   ```
   [client]
   host = <host_url>
   port = <MySQL_port>
   user = <username>
   password = <password>
   ```
1. Run the Django server.
   ```
   python3 manage.py runserver
   ```
1. Visit `127.0.0.1:8000` to view the Product Registry.

### Development Environment Setup with Docker

A Dockerfile is provided to set up an Ubuntu Linux container for this project.
The following steps set up the container.

1. Install [Docker](https://docs.docker.com/engine/install/).
1. Open a terminal and change directory into the root directory of the Product Registry code (i.e., where the pyproject.yaml file is).
1. Create a database credentials file named `db.cnf` in the root directory of the Product Registry code with the following contents:
   ```
   [client]
   host = <host_url>
   port = <MySQL_port>
   user = <username>
   password = <password>
   ```
   Replace the angle bracket placeholders with the database credentials.
1. Build a Docker image from the Dockerfile.
   ```
   docker build -t orange-button-productregistry .
   ```
1. Run a Docker container using the image.
   ```
   docker run --rm -dti --name obpr --ipc host --hostname <username> -p 8000:8000 -v <pwd>:/root/Orange-Button-ProductRegistry orange-button-productregistry:latest /bin/bash
   ```
   where `<username>` is a username for the container, and `<pwd>` is the __absolute__ path to the root directory of the Product Registry code.
   The `-v` flag mounts the Product Registry code directory so that it can be edited and saved outside of the Docker container.
1. Open a Bash shell in the Docker container.
   ```
   docker exec -it obpr /bin/bash
   ```
1. Activate the Python virtual environment.
   ```
   source .venv/bin/activate
   ```
1. Run the Django server.
   ```
   python3 manage.py runserver 0.0.0.0:8000
   ```
1. Visit `127.0.0.1:8000` to view the Product Registry.

### Creating the database on the MySQL server.

1. Log onto the MySQL database using, for example, [MySQL client](https://dev.mysql.com/doc/refman/8.4/en/mysql.html).
1. Create a new database on the MySQL server with the command:
   ```
   CREATE DATABASE <database_name> CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs;
   ```
   where `<database_name>` is the name of the database (e.g., `product_registry`).
1. In `product_registry/settings.py`, set `DATABASES['default']['NAME']` equal to `<database_name>`.
1. Run `python3 manage.py makemigrations` and then `python3 manage.py migrate` to create the database tables.


Updated the Dockerfile to run migrations, activate virtual environment and to run manage.py