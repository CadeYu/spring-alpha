## ---- Stage 1: Build ----
FROM node:20-alpine AS build

WORKDIR /app

# Cache dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source
COPY . .

# Build with standalone output
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

## ---- Stage 2: Runtime ----
FROM node:20-alpine

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Copy standalone build output
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
