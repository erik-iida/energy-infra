from . import collect, derive, render  # noqa: F401

print(__import__("jobs").__doc__)
for mod in (collect, derive, render):
    print(f"python -m {mod.__name__}")
    w = max(len(k) for k in mod.TABLE)
    for k, (h, _) in mod.TABLE.items():
        print(f"  {k:{w}}  {h}")
    print()
