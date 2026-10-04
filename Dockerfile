# GridEconomics back end: one image for every job (python -m jobs.<collect|derive|render|hourly|publish> ...).
# Used by Render's cron jobs (render.yaml); GitHub Actions keeps installing from the requirements files directly.
#
#   docker build -t gridecon .
#   docker run --rm -e STORE_BACKEND=local -e STORE_DIR=/data -v $PWD/store:/data gridecon python -m jobs
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
# h5py / PyWake wheels are self-contained; shapely needs libgeos only when building from source (wheels include it)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata curl \
    && rm -rf /var/lib/apt/lists/*
# node + wrangler: `jobs.publish cloudflare` uploads dist/ to Cloudflare Pages (the public site) and site_private/
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g wrangler@4 --no-audit --no-fund && npm cache clean --force

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY requirements.lock ./
RUN uv pip install --system --no-cache -r requirements.lock

COPY . .
# scratch that must survive between runs (forecast / wake / ENTSO-E caches) is synced from the bucket by jobs.hourly
ENV STATE_DIR=/tmp/state BUILD_DIR=/tmp/build DIST_DIR=/tmp/dist STORE_CACHE=/tmp/store-cache
CMD ["python", "-m", "jobs"]
