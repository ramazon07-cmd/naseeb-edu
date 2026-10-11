FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=/api
ARG VITE_SHOW_DEMO_ACCOUNTS=false
# Object-storage origin(s) the browser downloads private files from (CSP connect-src).
ARG FILE_STORAGE_ORIGINS=
# Where nginx proxies /api when VITE_API_URL is relative (same origin, needed by
# the HttpOnly refresh cookie), e.g. http://backend:8000 or https://api.example.com.
ARG API_UPSTREAM=
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_SHOW_DEMO_ACCOUNTS=$VITE_SHOW_DEMO_ACCOUNTS
ENV FILE_STORAGE_ORIGINS=$FILE_STORAGE_ORIGINS
ENV API_UPSTREAM=$API_UPSTREAM
RUN npm run build \
 && node scripts/render-nginx-conf.mjs nginx.conf dist/index.html "$VITE_API_URL" > /app/nginx.rendered.conf

FROM nginx:1.27-alpine
COPY --from=build /app/nginx.rendered.conf /etc/nginx/conf.d/default.conf
COPY nginx-security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
