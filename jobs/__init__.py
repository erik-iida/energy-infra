"""The back end as three jobs (spec 2 / spec 3 step 4): the commands the workflows call today and Render's cron jobs call next.

    python -m jobs.collect <source> [args]   source -> data store (Parquet) or data/static/ (committed inputs)
    python -m jobs.derive  <what>   [args]   store / forecasts -> derived data (feed.json, daily metrics, newsletter facts)
    python -m jobs.render  <what>   [args]   derived data -> the site files (build/) and the deployable site (dist/)

Each subcommand runs the existing module or script exactly as the command line did (same arguments, same output),
so switching a workflow to `python -m jobs...` changes nothing but the name. `python -m jobs` lists everything.
"""
