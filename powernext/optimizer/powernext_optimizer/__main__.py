import argparse
import json
from pathlib import Path
from .common import log, RequestError


def main():
    parser=argparse.ArgumentParser(description="PowerNext exhaustive inverse recommendation engine")
    sub=parser.add_subparsers(dest="command",required=True)
    rec=sub.add_parser("recommend")
    rec.add_argument("--request",required=True,type=Path)
    rec.add_argument("--output",required=True,type=Path)
    rec.add_argument("--workers",type=int,default=4)
    rec.add_argument("--cache",type=Path)
    rec.add_argument("--registry",type=Path)
    rec.add_argument("--selection",type=Path)
    rec.add_argument("--adapter",default="provisional")
    rec.add_argument("--history",type=Path)
    rec.add_argument("--quiet",action="store_true")
    args=parser.parse_args()
    def reject(value):
        raise ValueError(f"Nonfinite JSON value: {value}")
    try:
        raw=json.loads(args.request.read_text(encoding="utf-8"),parse_constant=reject)
        from .service import recommend
        from .storage import HistoryStore
        history=HistoryStore(args.history) if args.history else None
        result=recommend(raw,workers=args.workers,cache=args.cache,registry=args.registry,selection=args.selection,
            adapter_name=args.adapter,history=history,progress=not args.quiet)
        data=result.save(args.output,history)
        print(json.dumps(dict(status=data["status"],result_id=data.get("result_id"),output=str(args.output),
            best_candidate_id=data["best_configuration"]["candidate_id"] if data["best_configuration"] else None),allow_nan=False))
        return 2 if data["status"]=="INVALID_REQUEST" else 0
    except (ValueError,FileExistsError,OSError) as exc:
        log(f"ERROR: {exc}")
        return 2


if __name__=="__main__":
    raise SystemExit(main())
