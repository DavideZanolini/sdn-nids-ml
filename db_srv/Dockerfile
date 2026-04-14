FROM mariadb:10.6

ENV MYSQL_ROOT_PASSWORD=root
ENV MYSQL_DATABASE=shop

# Install ping utility for diagnostics
RUN apt-get update && DEBIAN_FRONTEND=noninteractive \
	apt-get install -y --no-install-recommends iputils-ping \
	&& rm -rf /var/lib/apt/lists/*

COPY init.sql /docker-entrypoint-initdb.d/
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 3306