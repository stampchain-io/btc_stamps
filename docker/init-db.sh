#!/bin/bash

echo "Creating database: $MYSQL_DATABASE with user $MYSQL_USER with all permisions"
echo "Creating database: $MYSQL_DATABASE with user $GRAFANA_USER with select permision"

cat << EOF > /docker-entrypoint-initdb.d/init-db.sql
CREATE DATABASE IF NOT EXISTS $MYSQL_DATABASE;
CREATE USER '$MYSQL_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$MYSQL_PASSWORD';
GRANT ALL PRIVILEGES ON $MYSQL_DATABASE.* TO '$MYSQL_USER'@'%';
CREATE USER '$GRAFANA_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$GRAFANA_PASSWORD';
GRANT SELECT ON $MYSQL_DATABASE.* TO '$GRAFANA_USER'@'%';
FLUSH PRIVILEGES;
EOF

echo "Done!"