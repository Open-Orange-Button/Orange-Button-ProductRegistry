Orange Button Product Registry
==============================

Installation for development
============================

If you are new to `Django <https://www.djangoproject.com/>`_, first please read their `excellent tutorial <https://docs.djangoproject.com/en/6.0/intro/tutorial01/>`_.
It will explain much of the Product Registry's implementation.

Installing project dependencies
-------------------------------

#. Clone this repository and ``cd`` into it.

#. Install the `uv Python package manager <https://docs.astral.sh/uv/>`_:

   .. code:: bash

      curl -LsSf https://astral.sh/uv/install.sh | sh

#. Install the JSON command-line JSON processor `jq <https://jqlang.org/>`_.

#. Install the project's Python dependencies.

   .. code:: bash

      uv sync --dev

#. Activate the Python virtual environment.

   .. code:: bash

      source .venv/bin/activate

Building a local database
-------------------------

This project uses `SQLite <https://sqlite.org/>`_ as the database for local development.
To build a local SQLite Product Registry database,

#. Update the `Django migrations <https://docs.djangoproject.com/en/6.0/topics/migrations/>`_ to match the `Django model definitions <https://docs.djangoproject.com/en/6.0/topics/db/models/>`_.
   ``No changes detected`` means that they are up-to-date.

   .. code:: bash

      python manage.py makemigrations

#. Apply the migrations to the database to create all the tables.

   .. code:: bash

      python manage.py migrate

Now that the database is built, we will populate it using Jupyter Notebooks.

#. In another terminal window, start a Jupyter Notebook server by running

   .. code:: bash

      uv run jupyter lab .

#. The Django app ``ob_taxonomy`` defines tables for storing the `Orange Button Taxonomy <https://github.com/Open-Orange-Button/Orange-Button-Taxonomy>`_ as database metadata that is referenced frequently in the Product Registry's code.
   Populate these tables by running the notebook ``ob_taxonomy/upload_taxonomy.ipynb`` (note that `jq <https://jqlang.org/>`_ must be installed).

#. In ``server/data_upsert``, there are multiple Jupyter Notebooks for cleaning and uploading CEC data.
   Run each of these notebooks to output cleaned CEC data:

   - For ``ProdBattery``, run the notebook ``server/data_upsert/ProdBattery/clean.ipynb``.
   - For ``ProdModule``, run the notebook ``server/data_upsert/ProdModule/clean.ipynb``.

#. With the cleaned data, upload the the CEC data.

   - For ``ProdBattery``, run the notebook ``server/data_upsert/ProdBattery/upsert_no_orm.ipynb``.
   - For ``ProdModule``, run the notebook ``server/data_upsert/ProdModule/upsert_no_orm.ipynb``.

Running a development server
----------------------------

Start a development server by running

.. code:: bash

   python manage.py runserver

Deployment
==========

This project is set up to be deployed on `Amazon (AWS) Elastic Container Service (ECS) <https://aws.amazon.com/ecs/>`_ with a `MySQL <https://www.mysql.com/>`_ database, where "Container" refers to a `Docker container <https://www.docker.com/>`_.
Configuring AWS deployment infrastructure though their developer console is tedious and difficult to do consistently, so this project uses `Terraform <https://developer.hashicorp.com/terraform>`_ to automate the configuration instead.

Infrastructure configuration with Terraform
-------------------------------------------

These are roughly the steps to follow.
Depending on what infrastructure already exists (e.g., HTTPS certificates for the domain), you may need to do additional steps.

#. In ``terraform/variables.tf``, edit the variables ``service-name``, ``service-name-alphanumeric``, and ``service-domain-name``.

#. In ``terraform/bastion.tf``, edit the ``aws_security_group`` called ``bastion_sg`` by writing your IP address in the ``ingress`` ``cidr_block``.
   This "Bastion" EC2 server is needed later for connecting to the database to upload data.

#. In ``terraform/database.tf``, edit the ``password`` field of the ``aws_db_instance`` called ``mysql``.

#. ``cd`` into ``terraform``.

#. Create an SSH key pair for connecting to the "Bastion" EC2 instance later: ``ssh-keygen -f bastion_key``.

#. Run ``terraform init``.

#. Use the `AWS command-line interface <https://aws.amazon.com/cli/>`_ to log into AWS by running ``aws login``.

#. Run ``terraform plan`` to see what infrastructure will be configured (additions, changes, and deletions).

#. Run ``terraform apply`` to perform the infrastructure configuration.

#. Note the final outputs of ``terraform apply``.
   They include the following:

   - An `Amazon Elastic Container Registry (ECR) <https://aws.amazon.com/ecr/>`_ address to which we will push a Docker image of this project.
   - The IP address of the "Bastion" EC2 instance we will use a proxy to connect to the database.

Pushing a Docker image to `Amazon Elastic Container Registry (ECR) <https://aws.amazon.com/ecr/>`_
--------------------------------------------------------------------------------------------------

#. Rename ``product_registry/settings_deployment.py`` to ``product_registry/settings.py`` and replace the appropriate values (e.g., ``SECRET_KEY``, ``ALLOWED_HOSTS``, etc.).

#. Build the Docker image.

   .. code:: bash

      docker build -t django-ecs .  # django-ecs is an arbitrary name for the image

#. Debugging the image. With Django's HTTPS redirection turned off, try

   .. code:: bash

      docker run --rm -p 8000:8000 --name django-test django-ecs --bind 0.0.0.0:8000

   and then go to ``127.0.0.1``.

#. Log Docker into AWS.

   .. code:: bash

      aws ecr get-login-password --region us-<REGION>-1 | docker login --username AWS --password-stdin <AWS_ACCOUNT_NUMBER>.dkr.ecr.us-<REGION>-1.amazonaws.com

   .. note::

      If you used ``sudo docker`` to build the image, you must also use ``sudo docker`` here.

#. Tag the Docker image.

   .. code:: bash

      docker tag django-ecs:latest <AWS_ACCOUNT_NUMBER>.dkr.ecr.us-<REGION>-1.amazonaws.com/<ECR_REPO_NAME>:latest

#. Push the Docker image to AWS ECR.

   .. code:: bash

      docker push <AWS_ACCOUNT_NUMBER>.dkr.ecr.us-<REGION>-1.amazonaws.com/<ECR_REPO_NAME>:latest

#. Look the `load balancer <https://aws.amazon.com/elasticloadbalancing/application-load-balancer/>`_ page in the AWS developer console to find the ECS task and check whether the task instances are running.
   Look at the logs in `AWS CloudWatch <https://aws.amazon.com/cloudwatch/>`_ to debug.

#. Once an ECS task instance is running, it will automatically create the tables in the database.

#. If you are building an image to replace the current one in production, AWS ECS will not automatically use the newly built image if it has the same tag (e.g., "latest") as the old image.
   To get AWS ECS to use the new image, navigate to the ECS service following breadcrumbs like

   .. code::

      Amazon Elastic Container Service > Clusters > ob-product-registry-2026-02-cluster > Services > ob-product-registry-2026-02-service > Health

   In the top right, there should be a button labeled "Update service".
   Click the dropdown next to it and select "Force new deployment".

Connecting and uploading data to the database
---------------------------------------------

The database is in a private subnet of the virtual private cloud (VPC) we created, so we cannot connect to it directly to upload data.
Instead, we use a temporary "Bastion" EC2 instance as a proxy.
Run

.. code:: bash

   ssh -i bastion_key -L 3307:<DATABASE_URL>:3306 ec2-user@<BASTION_EC2_IP>

where we intentionally linked port 3307 of our local machine to port 3306 of the database.
You can find the ``DATABASE_URL`` in the AWS Relational Database Service section of the AWS developer console.

Now, we can connect to the database by running

.. code:: bash

   mysql -h 127.0.0.1 -P 3307 -u admin -p

and entering the password in ``terraform/database.tf``.

To upload data into the database, one successful technique is as follows:

#. Build a local SQLite database containing all the data to be uploaded to the remote production MySQL database.

#. Use `DuckDB <https://duckdb.org/>`_ to connect to both the local SQLite database than the remote database.

   .. code:: sql

      attach 'db.sqlite3' as lds (type sqlite);
      attach 'host=localhost user=admin password=<DATABASE_PASSWORD> database=OBProductRegistry port=3307' as rds (type mysql);

#. In DuckDB, select data from the local database to upsert into the remote database.
   Here is an example of **inserting** ``ProdBattery`` and ``ProdModule`` data:

   .. code:: sql

      begin transaction;
      insert into rds.server_dcinput select * from lds.server_dcinput;
      insert into rds.server_dcoutput select * from lds.server_dcoutput;
      insert into rds.server_dimension select * from lds.server_dimension;
      insert into rds.server_product select * from lds.server_product;
      insert into rds.server_prodbattery select * from lds.server_prodbattery;
      insert into rds.server_entity select * from lds.server_entity;
      insert into rds.server_certificationagency select * from lds.server_certificationagency;
      insert into rds.server_checksum select * from lds.server_checksum;
      insert into rds.server_firmware select * from lds.server_firmware;
      insert into rds.server_prodcertification select * from lds.server_prodcertification;
      insert into rds.server_product_ProdCertifications select * from lds.server_product_ProdCertifications;
      insert into rds.server_prodcell select * from lds.server_prodcell;
      insert into rds.server_prodglazing select * from lds.server_prodglazing;
      insert into rds.server_moduleelectrating select * from lds.server_moduleelectrating;
      insert into rds.server_prodmodule select * from lds.server_prodmodule;
      insert into rds.server_prodmodule_ModuleElectRatings select * from lds.server_prodmodule_ModuleElectRatings;
      insert into rds.server_sourcecountry select * from lds.server_sourcecountry;
      insert into rds.server_product_SourceCountries select * from lds.server_product_SourceCountries;
      commit;

#. Once all the data is uploaded, destroy the "Bastion" EC2 instance to save costs.
   In ``terraform/bastion.tf``, comment out everything except the ``aws_security_group`` named ``bastion_sg``.
   In ``terraform/security_groups.tf``, remove ``aws_security_group.bastion_sg.id`` from the ``security_groups`` of ``ingress`` of the ``aws_security_group`` named ``rds_sg``.
   Run ``terraform apply`` to remove the security group from the database and destroy the "Bastion" EC2 instance.
   Next, in ``terraform/bastion.tf``, comment out the ``aws_security_group`` named ``bastion_sg``.
   Rerun ``terraform apply`` to destroy the Bastion's security group.

Serving the website from the domain
-----------------------------------

Enter the domain and the load balancer's URL into your domain provider's DNS CNAME table.
