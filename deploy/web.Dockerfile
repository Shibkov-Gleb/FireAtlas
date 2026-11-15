FROM node:22-bookworm-slim AS build
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@10.28.2 --activate
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN --mount=type=cache,id=fire-atlas-pnpm,target=/pnpm/store pnpm install --frozen-lockfile --store-dir /pnpm/store
COPY apps/web apps/web
COPY packages/contracts/dictionaries.ru.json packages/contracts/dictionaries.ru.json
COPY scripts/check-build.mjs scripts/check-build.mjs
RUN pnpm build && pnpm build:check

FROM nginx:1.28-alpine
COPY deploy/nginx.local.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/apps/web/dist /srv/fire-atlas/web
EXPOSE 80
