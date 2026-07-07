# =============================================================================
# Helix SCO web container (Phase 5)
# =============================================================================
# Multi-stage arm64 build: Vite/React static assets served by nginx.
# The browser calls same-origin /api/*; nginx injects X-API-Key server-side.
# =============================================================================

FROM node:22-bookworm-slim AS build

WORKDIR /app
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM nginx:1.27-bookworm

COPY docker/web/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
