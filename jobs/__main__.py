from . import collect, derive, publish, render  # noqa: F401

print(__import__("jobs").__doc__)
for mod in (collect, derive, render, publish):
    print(f"python -m {mod.__name__}")
    w = max(len(k) for k in mod.TABLE)
    for k, (h, _) in mod.TABLE.items():
        print(f"  {k:{w}}  {h}")
    print()
print("python -m jobs.hourly [--no-publish] [--tabs always|3h|never]   the whole hourly run (Render cron): derive feed, render tabs + site, publish")
