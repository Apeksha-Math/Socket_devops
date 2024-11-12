# Use an official Python runtime as a parent image
FROM python:3.9.10-slim

# Set the working directory inside the container
WORKDIR /usr/src/app

# Install necessary dependencies for pyodbc and Microsoft ODBC driver
RUN apt-get update && \
    apt-get install -y curl gnupg unixodbc-dev gcc g++ && \
    apt-get clean

# Install Microsoft ODBC Driver for SQL Server (if needed for pyodbc)
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/10/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17

RUN pip install pyodbc

# Copy your application code into the container
COPY . .

# Create a volume for logs
VOLUME /usr/src/app/logs

# Expose the port the app runs on
EXPOSE 9010

# Command to run when starting the container
CMD ["python", "./server.py", "STAGING"]
