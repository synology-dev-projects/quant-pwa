FROM nginx:alpine

# Copy static frontend files to nginx html root
COPY . /usr/share/nginx/html

# Copy custom nginx configuration template (nginx:alpine runs envsubst automatically)
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
