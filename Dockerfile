# Use Python base image
FROM python:3.10-slim

# Set environment variable to silence frontend errors
ENV DEBIAN_FRONTEND=noninteractive

# Install core tools + Microsoft SQL ODBC 17 Driver
RUN apt-get update && \
    apt-get install -y \
    gnupg2 curl unixodbc-dev gcc g++ make \
    libpq-dev libssl-dev apt-transport-https ca-certificates && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create and switch to app directory
WORKDIR /app

# Copy source code
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Run with gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]
