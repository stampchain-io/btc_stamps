#!/bin/bash

# Asume que las variables de entorno como MYSQL_DATABASE, MYSQL_USER,
# MYSQL_PASSWORD, etc., están establecidas por Docker o en el entorno de ejecución.

echo "Creating database: $MYSQL_DATABASE with user $MYSQL_USER with all permissions"
echo "Creating database: $MYSQL_DATABASE with user $GRAFANA_USER with select permission"
echo "Creating database: $MYSQL_DATABASE with user $APP_USER with select permission"

# FIXME: caching_sha2_password
mysql -u root -p"$MYSQL_ROOT_PASSWORD" <<-EOSQL
    CREATE DATABASE IF NOT EXISTS \`$MYSQL_DATABASE\`;
    CREATE USER IF NOT EXISTS '$MYSQL_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$MYSQL_PASSWORD';
    GRANT ALL PRIVILEGES ON \`$MYSQL_DATABASE\`.* TO '$MYSQL_USER'@'%';
    CREATE USER '$GRAFANA_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$GRAFANA_PASSWORD';
    GRANT SELECT ON \`$MYSQL_DATABASE\`.* TO '$GRAFANA_USER'@'%';
    CREATE USER '$APP_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$APP_PASSWORD';
    GRANT SELECT ON \`$MYSQL_DATABASE\`.* TO '$APP_USER'@'%';
    FLUSH PRIVILEGES;
EOSQL

echo "Done!"
