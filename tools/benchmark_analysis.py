"""Reproducible UCI analysis timings; each sample starts with a cold engine."""
import argparse
import json
import time
from pathlib import Path

import chess
import chess.engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True, type=Path)
    parser.add_argument('--depth', type=int, default=20)
    parser.add_argument('--multipv', type=int, default=3)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--seconds', type=float, default=120)
    parser.add_argument('--runs', type=int, default=1)
    parser.add_argument('--fen', default=chess.STARTING_FEN)
    args = parser.parse_args()
    for run in range(args.runs):
        with chess.engine.SimpleEngine.popen_uci(str(args.engine.resolve())) as engine:
            engine.configure({'OwnBook': False, 'NNUE': False, 'SearchProfile': 'Optimized',
                              'Threads': args.threads, 'Hash': 256})
            start = time.perf_counter()
            result = engine.analyse(chess.Board(args.fen),
                                    chess.engine.Limit(depth=args.depth, time=args.seconds),
                                    multipv=args.multipv)
            print(json.dumps({'run': run + 1, 'engine': str(args.engine), 'fen': args.fen,
                              'target_depth': args.depth, 'multipv': args.multipv,
                              'threads': args.threads, 'seconds': round(time.perf_counter()-start, 3),
                              'depths': [info.get('depth') for info in result],
                              'nodes': result[0].get('nodes'),
                              'moves': [info['pv'][0].uci() for info in result],
                              'scores': [str(info['score']) for info in result]}), flush=True)


if __name__ == '__main__':
    main()
