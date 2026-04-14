#!/bin/bash
echo "Build docker image for the web server."
docker build -t web_server -f web_srv/Dockerfile web_srv/

echo "Build docker image for the database server."
docker build -t db_server -f db_srv/Dockerfile db_srv/