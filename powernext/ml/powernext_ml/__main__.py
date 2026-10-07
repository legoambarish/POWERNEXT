import argparse
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description="PowerNext data and ML development CLI")
    sub=p.add_subparsers(dest="command",required=True)
    g=sub.add_parser("generate")
    g.add_argument("--output",type=Path,required=True)
    g.add_argument("--samples-per-stratum",type=int,default=12)
    g.add_argument("--seed",type=int,default=20261002)
    g.add_argument("--workers",type=int,default=4)
    g.add_argument("--n-points",type=int,default=1600)
    g.add_argument("--adapter",default="provisional")
    a=sub.add_parser("audit-legacy")
    a.add_argument("--workbook",type=Path,required=True)
    a.add_argument("--output",type=Path,required=True)
    a=sub.add_parser("benchmark")
    a.add_argument("--domain",choices=["legacy","simulation"],required=True)
    a.add_argument("--data",type=Path,required=True)
    a.add_argument("--output",type=Path,required=True)
    a.add_argument("--registry",type=Path,required=True)
    a=sub.add_parser("predict")
    a.add_argument("--registry",type=Path,required=True)
    a.add_argument("--selection",type=Path,required=True)
    a.add_argument("--adapter",default="provisional")
    a.add_argument("--request",type=Path,required=True)
    a.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.command=="generate":
        from .generate import generate
        generate(args.output,args.samples_per_stratum,args.seed,args.workers,args.n_points,args.adapter)
    elif args.command=="audit-legacy":
        from .legacy import audit
        audit(args.workbook,args.output)
    elif args.command=="benchmark":
        from .training import benchmark
        benchmark(args.domain,args.data,args.output,args.registry)
    elif args.command=="predict":
        import json
        from .inference import predict
        from .common import write_json
        write_json(args.output,predict(json.loads(args.request.read_text()),args.registry,args.selection,args.adapter))


if __name__=="__main__": main()
