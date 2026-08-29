FROM nginx:alpine

# Copy static frontend files to nginx html root
COPY . /usr/share/nginx/html

# Copy template for dynamic gateway host proxying
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

ENV NGINX_ENVSUBST_FILTER=GATEWAY_HOST
ENV GATEWAY_HOST=quant-gateway-prod

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
