#!/bin/bash
DATA_DIR="/var/lib/mysql"

if [ ! -d "$DATA_DIR/mysql" ]; then
    mysql_install_db --user=root --datadir="$DATA_DIR" --skip-test-db > /dev/null 2>&1
    mysqld_safe --user=root --datadir="$DATA_DIR" --skip-networking &
    for i in $(seq 1 30); do
        mysqladmin -u root ping --silent 2>/dev/null && break
        sleep 1
    done
    mysql -u root <<-SQL
        ALTER USER 'root'@'localhost' IDENTIFIED BY 'root';
        CREATE DATABASE IF NOT EXISTS shop;
        USE shop;
        SOURCE /docker-entrypoint-initdb.d/init.sql;
        FLUSH PRIVILEGES;
SQL
    mysqladmin -u root -proot shutdown 2>/dev/null
    sleep 2
fi

exec mysqld_safe --user=root --datadir="$DATA_DIR" --bind-address=0.0.0.0