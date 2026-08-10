"""CLI: nemsynth gen --scenario chest-pain --seed 1 --count 10 -o out/"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import distributions, messiness
from .generate import SCENARIOS, generate_mci, scenario_for, generate_one
from .validate import SUPPORTED_VERSIONS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nemsynth")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("gen", help="generate synthetic NEMSIS documents")
    gen.add_argument(
        "--mci", type=int, default=0, metavar="N",
        help="emit mass-casualty incidents of N patients: one EMSDataSet per "
             "file holding N PatientCareReports that share the incident")
    gen.add_argument(
        "--scenario", default="mixed", choices=["mixed", *sorted(SCENARIOS)],
        help="a single presentation, or 'mixed' (default) to rotate the whole "
             "library across seeds — what a real agency's export looks like")
    gen.add_argument("--seed", type=int, default=1)
    gen.add_argument("--count", type=int, default=1)
    gen.add_argument("--version", default="3.5.0", choices=SUPPORTED_VERSIONS)
    gen.add_argument("--messiness", default="medium",
                     choices=sorted(messiness.PROFILES),
                     help="how much realistic imperfection to inject "
                          "(clean = fully populated; high = stress)")
    gen.add_argument("-o", "--out", required=True, help="output directory")

    sub.add_parser("sources", help="show where the distributions come from")

    args = parser.parse_args(argv)

    if args.command == "sources":
        source = distributions.source()
        print(f"  {source['title']} — {source['publisher']}")
        print(f"  {source['url']}")
        print(f"  basis: {source['basis']}  (retrieved {source['retrieved']})")
        print()
        for name in ("service_type", "level_of_care", "disposition", "sex",
                     "transport_method", "dispatch_reason_approx",
                     "age_years_approx"):
            kind = "measured " if distributions.is_measured(name) else "ASSUMED  "
            print(f"  {kind} {name}")
        print("\n  ASSUMED distributions are working assumptions, not national")
        print("  data — see the reasoning in data/national_distributions.json.")
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for offset in range(args.count):
        seed = args.seed + offset
        if args.mci:
            document = generate_mci(seed, args.mci, args.version,
                                    profile=args.messiness)
            path = out / f"mci{args.mci}-{seed:08d}.xml"
        else:
            document = generate_one(seed, scenario_for(seed, args.scenario),
                                    args.version, profile=args.messiness)
            path = out / f"{scenario_for(seed, args.scenario)}-{seed:08d}.xml"
        path.write_bytes(document)
    print(f"wrote {args.count} document(s) to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
