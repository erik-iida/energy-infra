# GridEconomics back end: one image for every job (python -m jobs.<collect|derive|render|hourly|publish> ...).
# Used by Render's cron jobs (render.yaml); GitHub Actions keeps installing from the requirements files directly.
#
#   docker build -t gridecon .
#   docker run --rm -e STORE_BACKEND=local -e STORE_DIR=/data -v $PWD/store:/data gridecon python -m jobs
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
# h5py / PyWake wheels are self-contained; shapely needs libgeos only when building from source (wheels include it)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY requirements.lock ./
RUN uv pip install --system --no-cache -r requirements.lock

COPY . .
# scratch that must survive between runs (forecast / wake / ENTSO-E caches) is synced from the bucket by jobs.hourly
ENV STATE_DIR=/tmp/state BUILD_DIR=/tmp/build DIST_DIR=/tmp/dist STORE_CACHE=/tmp/store-cache
CMD ["python", "-m", "jobs"]
