"""Portable v3 search subprocess boundary with explicit artifact destinations."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from .application import normalize_public_request
from .optimizer import recommend, save_result


def main(argv=None):
    parser=argparse.ArgumentParser(description="PowerNext network optimizer v3")
    sub=parser.add_subparsers(dest="command",required=True)
    search=sub.add_parser("optimize")
    search.add_argument("--request",type=Path,required=True)
    search.add_argument("--output",type=Path,required=True,help="New artifact directory; never overwrite a result")
    search.add_argument("--registry",type=Path)
    search.add_argument("--selection",type=Path)
    args=parser.parse_args(argv)
    if hasattr(sys.stdout,"reconfigure"):sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    def progress(message):print(f"[{datetime.now(timezone.utc).isoformat()}] {message}",flush=True)
    request=json.loads(args.request.read_text(encoding="utf-8"))
    # Validate the public active scope before touching the destination or
    # starting the optimizer.  Historical four-module artifacts remain usable
    # through their low-level APIs but are not a live CLI request shape.
    request,_=normalize_public_request(request)
    if args.output.exists():raise FileExistsError("Result directory already exists; preserve immutable evidence")
    progress("Starting network search")
    result,waveforms=recommend(request,registry=args.registry,selection=args.selection,progress=progress)
    save_result(result,waveforms,args.output)
    progress(f"Saved {result['status']}; catalog_complete={result['search']['catalog_complete']}")
    return 0


if __name__=="__main__":sys.exit(main())
