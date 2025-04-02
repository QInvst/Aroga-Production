FROM python:3.10-slim

# Set environment variable to silence frontend errors
ENV DEBIAN_FRONTEND=noninteractive

# Install base tools
RUN apt-get update && \
    apt-get install -y \
    gnupg2 curl gcc g++ make apt-transport-https ca-certificates libssl-dev libpq-dev && \
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev --allow-downgrades --allow-remove-essential --allow-change-held-packages && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy app code
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Start app
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]
