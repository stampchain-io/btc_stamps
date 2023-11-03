#!/bin/bash
# init-db.sh
echo "Creating database: $MYSQL_DATABASE"

cat << EOF > /docker-entrypoint-initdb.d/init-db.sql
CREATE USER '$MYSQL_USER'@'%' IDENTIFIED BY '$MYSQL_PASSWORD';
GRANT ALL PRIVILEGES ON $MYSQL_DATABASE.* TO '$MYSQL_USER'@'%';
FLUSH PRIVILEGES;
EOF

echo "Done!"