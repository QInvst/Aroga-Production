FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install required base dependencies
RUN apt-get update && apt-get install -y \
    gnupg2 curl apt-transport-https ca-certificates \
    build-essential gcc g++ make pkg-config \
    libssl-dev libpq-dev default-libmysqlclient-dev \
    && apt-get clean

# Add Microsoft SQL Server ODBC Driver 17 repo
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update

# Remove conflicting ODBC packages to prevent dpkg overwrite issues
RUN apt-get remove -y unixodbc-common unixodbc libodbc2 libodbcinst2 || true

# Install MS ODBC Driver 17 and unixodbc-dev
RUN ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev

# Set working directory
WORKDIR /app

# Copy source code
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip && pip install -r requirements.txt

# Run app with gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]
