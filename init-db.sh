#!/bin/bash

echo "Creating database: $MYSQL_DATABASE with user $MYSQL_USER"

cat << EOF > /docker-entrypoint-initdb.d/init-db.sql
CREATE DATABASE IF NOT EXISTS $MYSQL_DATABASE;
CREATE USER '$MYSQL_USER'@'%' IDENTIFIED WITH mysql_native_password BY '$MYSQL_PASSWORD';
GRANT ALL PRIVILEGES ON $MYSQL_DATABASE.* TO '$MYSQL_USER'@'%';
FLUSH PRIVILEGES;
EOF

echo "Done!"