"""A project is one folder holding one county + trade build:

    my-list/
      county.yaml        where the data comes from and what the local codes mean
      trade.yaml         segments, classification rules, scoring and outreach angles
      firm_aliases.csv   optional: verified management firms (see docs)
      contacts.csv       optional: business contacts found in the contacts step
      raw/               downloaded source files
      work/              intermediate parquet files
      output/            the workbook, CSVs, Clay imports, call sheet, alerts
"""
import re
import shutil
import time
from pathlib import Path

import yaml

CONFIGS = Path(__file__).resolve().parent / "configs"
_t0 = time.time()


def log(msg):
    print(f"[{time.time() - _t0:6.0f}s] {msg}", flush=True)


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def builtin(kind):
    """Names of the bundled county or trade configs."""
    return sorted(p.stem for p in (CONFIGS / kind).glob("*.yaml"))


class Project:
    def __init__(self, path):
        self.dir = Path(path).expanduser().resolve()
        if not (self.dir / "county.yaml").exists():
            raise SystemExit(f"{self.dir} has no county.yaml. Run: canopy-leads init {path} --county <name> --trade <name>")
        self.county = load_yaml(self.dir / "county.yaml")
        self.trade = load_yaml(self.dir / "trade.yaml")
        self.raw = self.dir / "raw"
        self.work = self.dir / "work"
        self.out = self.dir / "output"
        for d in (self.raw, self.work, self.out):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def name(self):
        return f"{self.county.get('name', 'county')} – {self.trade.get('name', 'trade')}"

    @property
    def file_stem(self):
        return slug(f"{self.county.get('short_name', self.county.get('name', 'county'))}_{self.trade.get('id', 'leads')}")

    def segments(self):
        """{segment id: segment settings} in the order the trade lists them."""
        return {s["id"]: s for s in self.trade["segments"]}

    def label(self, seg_id):
        return self.segments().get(seg_id, {}).get("label", seg_id)


def init_project(path, county, trade, force=False):
    """Create a project folder with editable copies of the chosen configs."""
    d = Path(path).expanduser().resolve()
    d.mkdir(parents=True, exist_ok=True)
    for kind, name in (("counties", county), ("trades", trade)):
        src = Path(name) if Path(name).suffix in (".yaml", ".yml") else CONFIGS / kind / f"{name}.yaml"
        if not src.exists():
            raise SystemExit(f"No {kind[:-1]} config '{name}'. Bundled: {', '.join(builtin(kind))}")
        dst = d / ("county.yaml" if kind == "counties" else "trade.yaml")
        if dst.exists() and not force:
            print(f"kept existing {dst.name}")
            continue
        shutil.copy(src, dst)
        print(f"wrote {dst}")
    example = CONFIGS / "firm_aliases.example.csv"
    if not (d / "firm_aliases.csv").exists():
        shutil.copy(example, d / "firm_aliases.csv")
    for sub in ("raw", "work", "output"):
        (d / sub).mkdir(exist_ok=True)
    return d
