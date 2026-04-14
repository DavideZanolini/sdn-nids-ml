FROM nginx:alpine

# Install bash and python3 for running web_server.py
RUN apk add --no-cache bash python3

RUN rm /etc/nginx/conf.d/default.conf
RUN mkdir -p /home/files
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY web_server.py /home/web_server.py
RUN chmod +x /home/web_server.py
EXPOSE 8000
CMD ["python3", "/home/web_server.py"]
