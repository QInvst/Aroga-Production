FROM python:3.11-slim

# Install required packages and ODBC driver 17
RUN apt-get update && apt-get install -y \
    gnupg2 curl unixodbc-dev gcc g++ make \
    libpq-dev libssl-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/10/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get clean

# Set work directory
WORKDIR /app

# Copy files
COPY . /app

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 10000

# Run the application
CMD ["gunicorn", "-b", "0.0.0.0:10000", "app:app"]
