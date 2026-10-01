#!/bin/bash
set -e

# Start service
service postgresql start

# Configure postgresql.conf to listen on all interfaces
PG_CONF=$(find /etc/postgresql -name postgresql.conf | head -n 1)
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/g" "$PG_CONF"
sed -i "s/listen_addresses = 'localhost'/listen_addresses = '*'/g" "$PG_CONF"

# Configure pg_hba.conf to allow md5 connections from all hosts
PG_HBA=$(find /etc/postgresql -name pg_hba.conf | head -n 1)
echo "host all all 127.0.0.1/32 md5" >> "$PG_HBA"
echo "host all all ::1/128 md5" >> "$PG_HBA"
echo "host all all all md5" >> "$PG_HBA"

# Restart postgresql to apply configuration
service postgresql restart

# Provision user and database
su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='fios'\" | grep -q 1 || psql -c \"CREATE USER fios WITH PASSWORD 'fios' SUPERUSER;\""
su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='fios'\" | grep -q 1 || psql -c \"CREATE DATABASE fios OWNER fios;\""

echo "POSTGRESQL_SETUP_SUCCESS"
