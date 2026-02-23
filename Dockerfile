FROM ghcr.io/astral-sh/uv:debian

# set work directory
WORKDIR /usr/src/app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    python3-dev \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

# copy project
COPY . .

# install dependencies
RUN uv sync --group mysql

# # Create a user with UID 1000 and GID 1000
# RUN groupadd -g 1000 appgroup && \
#     useradd -r -u 1000 -g appgroup appuser
# # Switch to this user
# USER 1000:1000

RUN chmod +x ./start.sh

# Expose the port Django runs on
EXPOSE 8000

# Run the application
ENTRYPOINT ["./start.sh"]
