FROM nginx:alpine
# При старте образ подставляет переменные окружения (MORZIK_SERVER) и кладёт результат в conf.d/default.conf.
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY index.html login.html telegram-web-app.js morzik.js morzik-dizzy.png /usr/share/nginx/html/
