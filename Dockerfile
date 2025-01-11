FROM ubuntu:22.04

SHELL ["/bin/bash", "-c"]

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt install -y \
    build-essential \
    git \
    python3 \
    python3-pip \
    python3-venv \
    libmysqlclient-dev \
    mysql-client \
    vim

RUN mkdir -p /root/Orange-Button-ProductRegistry

WORKDIR /root/Orange-Button-ProductRegistry

ADD requirements.txt requirements.txt

RUN python3 -m venv .venv

RUN source .venv/bin/activate \
    && pip3 install -r requirements.txt

ADD db.cnf /etc/Orange-Button-ProductRegistry/db.cnf

LABEL version="0.1"
