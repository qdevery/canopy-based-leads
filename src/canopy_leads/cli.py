"""canopy-leads: build a ranked account list from a county tax roll.

  canopy-leads demo  runs/demo                                   # synthetic county, offline, ~1 minute
  canopy-leads init  runs/harris --county harris_tx --trade tree_care
  canopy-leads fetch runs/harris                                 # roll, canopy, storm reports
  canopy-leads run   runs/harris                                 # every step below, in order
  canopy-leads normalize | classify | canopy | rollup | storms | score | export  runs/harris
  canopy-leads shortlist runs/harris --tiers A B                 # contact research list + credit estimate
  canopy-leads alert runs/harris --days 7                        # weekly storm-damage alert
"""
import argparse
import shutil
import sys

from . import project as pj

STEPS = ["normalize", "classify", "canopy", "rollup", "storms", "score", "export"]


def step(name, p):
    pj.log(f"── {name}")
    if name == "normalize":
        from .classify import normalize
        normalize(p)
    elif name == "classify":
        from .classify import classify
        classify(p)
    elif name == "canopy":
        from .canopy import canopy
        canopy(p)
    elif name == "rollup":
        from .rollup import rollup
        rollup(p)
    elif name == "storms":
        from .storms import storms
        storms(p)
    elif name == "score":
        from .score import score
        score(p)
    elif name == "export":
        from .export import export
        export(p)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="canopy-leads", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init", help="create a project folder with editable county and trade configs")
    s.add_argument("project")
    s.add_argument("--county", required=True, help=f"bundled: {', '.join(pj.builtin('counties'))} (or a path to a .yaml)")
    s.add_argument("--trade", required=True, help=f"bundled: {', '.join(pj.builtin('trades'))} (or a path to a .yaml)")
    s.add_argument("--force", action="store_true", help="overwrite existing county.yaml / trade.yaml")
    s = sub.add_parser("fetch", help="download the public source data into raw/")
    s.add_argument("project")
    s.add_argument("--what", nargs="+", default=["roll", "canopy", "storms"], choices=["roll", "canopy", "storms"])
    s.add_argument("--force", action="store_true", help="download again even if the file exists")
    s = sub.add_parser("run", help="run every step")
    s.add_argument("project")
    s.add_argument("--from", dest="start", choices=STEPS, default="normalize", help="start at this step")
    for name in STEPS:
        sub.add_parser(name, help=f"run only the {name} step").add_argument("project")
    s = sub.add_parser("shortlist", help="accounts to research for contacts, with a credit estimate (spends nothing)")
    s.add_argument("project")
    s.add_argument("--tiers", nargs="+", default=["A"])
    s.add_argument("--max-people", type=int, default=3)
    s = sub.add_parser("alert", help="storm-damage alert: accounts with a property near a new NWS report")
    s.add_argument("project")
    s.add_argument("--days", type=int, default=7)
    s.add_argument("--start")
    s.add_argument("--end")
    s.add_argument("--km", type=float, default=3.0)
    s.add_argument("--reports", help="use a saved IEM storm-report CSV instead of downloading")
    s = sub.add_parser("demo", help="build the synthetic Example County end to end (offline)")
    s.add_argument("project", nargs="?", default="runs/demo")
    sub.add_parser("list", help="list bundled county and trade configs")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        print("counties:", ", ".join(pj.builtin("counties")))
        print("trades:  ", ", ".join(pj.builtin("trades")))
    elif a.cmd == "init":
        d = pj.init_project(a.project, a.county, a.trade, a.force)
        print(f"\nNext: review {d / 'county.yaml'}, then  canopy-leads fetch {a.project}  and  canopy-leads run {a.project}")
    elif a.cmd == "fetch":
        from .fetch import run
        p = pj.Project(a.project)
        if p.county.get("demo"):
            sys.exit("The demo county has no downloads: run  canopy-leads demo  instead.")
        run(p, a.what, a.force)
    elif a.cmd == "run":
        p = pj.Project(a.project)
        for name in STEPS[STEPS.index(a.start):]:
            step(name, p)
    elif a.cmd in STEPS:
        step(a.cmd, pj.Project(a.project))
    elif a.cmd == "shortlist":
        from .export import shortlist
        shortlist(pj.Project(a.project), tuple(a.tiers), a.max_people)
    elif a.cmd == "alert":
        from .alert import alert
        alert(pj.Project(a.project), a.days, a.start, a.end, a.km, a.reports)
    elif a.cmd == "demo":
        from .alert import alert
        from .demo import build
        from .export import shortlist
        d = pj.init_project(a.project, "example_county", "tree_care", force=True)
        for sub_dir in ("work", "output"):
            shutil.rmtree(d / sub_dir, ignore_errors=True)
        p = pj.Project(d)
        build(p)
        for name in STEPS:
            step(name, p)
        shortlist(p, ("A", "B"))
        alert(p, reports=str(p.raw / "storms" / "demo_alert_reports.csv"), start="2026-11-01", end="2026-11-05")
        print(f"\nDone. Open {p.out}/ — start with {p.file_stem}_leads.xlsx and call_sheet_top50.md")


if __name__ == "__main__":
    main()
