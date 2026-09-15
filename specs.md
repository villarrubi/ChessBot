# Chess Engine — Technical Specification

**Project status:** Initial specification  
**Target:** Build a chess engine from scratch that can play autonomously, analyze games, explain evaluations, collect data from its own games, and progressively improve through learning.

---

## 1. Project goals

The engine must eventually be able to:

- Represent any legal chess position.
- Generate every legal move from a position.
- Detect check, checkmate, stalemate, repetition, the fifty-move rule, and insufficient material.
- Search future positions efficiently.
- Evaluate positions numerically.
- Select the best move under a configurable time constraint.
- Analyze complete games and identify inaccuracies, mistakes, and blunders.
- Produce an explainable breakdown of its static evaluation.
- Save positions, searches, games, and training data.
- Play against itself.
- Play against external chess engines/modules, including Stockfish, engines written by other developers, and previous versions of this engine.
- Start engine-vs-engine games from the normal initial position, from an arbitrary FEN, or after a forced opening/line prefix.
- Support controlled opening training (for example Grünfeld, Italian Game, Queen's Gambit, or an exact user-specified line).
- Choose between using its own opening database/book or calculating independently from move 1.
- Tune its own handcrafted evaluation parameters.
- Train and use a learned evaluation network.
- Compare new versions against previous versions automatically.
- Expose a standard UCI interface so it can be used from common chess GUIs.

The first versions must favor **correctness, observability, and explainability** over raw strength.

---

# 2. Non-goals for the first versions

The initial engine will not attempt to:

- Reproduce Stockfish strength.
- Implement distributed search.
- Implement GPU search.
- Use opening books as a substitute for search.
- Depend on Stockfish for move selection.
- Hide evaluation behind an opaque neural network from day one.
- Optimize every component before correctness is established.

External engines may later be used only for benchmarking, validation, or generating comparison datasets.

---

# 3. Recommended technology stack

## Core engine

**Language:** C++20

Reasons:

- Fast enough for millions of nodes per second.
- Fine-grained memory control.
- Excellent support for bitwise board operations.
- Suitable for multithreading.
- Common choice for production chess engines.
- Easy integration with UCI chess interfaces.

## Training and analysis tooling

**Language:** Python 3.12+

Used for:

- dataset generation
- experiment orchestration
- parameter tuning
- neural-network training
- plotting benchmark results
- self-play management
- PGN analysis
- regression reporting

## Optional libraries

Core engine should minimize dependencies.

Suggested:

- CMake
- Catch2 or GoogleTest
- fmt
- Python:
  - python-chess
  - NumPy
  - pandas
  - PyTorch
  - matplotlib

`python-chess` is allowed for tooling and validation, but the C++ engine must implement its own chess rules.

---

# 4. Repository structure

```text
chess-engine/
│
├── CMakeLists.txt
├── README.md
├── specs.md
│
├── src/
│   ├── main.cpp
│   │
│   ├── board/
│   │   ├── board.h
│   │   ├── board.cpp
│   │   ├── bitboard.h
│   │   ├── bitboard.cpp
│   │   ├── move.h
│   │   ├── move.cpp
│   │   ├── movegen.h
│   │   ├── movegen.cpp
│   │   ├── attack_tables.h
│   │   ├── attack_tables.cpp
│   │   ├── zobrist.h
│   │   └── zobrist.cpp
│   │
│   ├── search/
│   │   ├── search.h
│   │   ├── search.cpp
│   │   ├── ordering.h
│   │   ├── ordering.cpp
│   │   ├── transposition_table.h
│   │   ├── transposition_table.cpp
│   │   ├── time_manager.h
│   │   └── time_manager.cpp
│   │
│   ├── eval/
│   │   ├── evaluation.h
│   │   ├── evaluation.cpp
│   │   ├── material.cpp
│   │   ├── mobility.cpp
│   │   ├── pawns.cpp
│   │   ├── king_safety.cpp
│   │   ├── piece_square.cpp
│   │   ├── passed_pawns.cpp
│   │   └── explain.cpp
│   │
│   ├── engine/
│   │   ├── engine.h
│   │   ├── engine.cpp
│   │   ├── limits.h
│   │   └── result.h
│   │
│   ├── protocol/
│   │   ├── uci.h
│   │   └── uci.cpp
│   │
│   ├── openings/
│   │   ├── opening_book.h
│   │   ├── opening_book.cpp
│   │   ├── opening_db.h
│   │   └── opening_db.cpp
│   │
│   └── learning/
│       ├── feature_export.h
│       ├── feature_export.cpp
│       ├── nnue.h
│       └── nnue.cpp
│
├── tests/
│   ├── test_board.cpp
│   ├── test_movegen.cpp
│   ├── test_perft.cpp
│   ├── test_zobrist.cpp
│   ├── test_eval.cpp
│   ├── test_search.cpp
│   └── positions/
│
├── tools/
│   ├── selfplay.py
│   ├── benchmark.py
│   ├── analyze_pgn.py
│   ├── tune_eval.py
│   ├── train_network.py
│   ├── compare_engines.py
│   ├── match_runner.py
│   ├── opening_suite.py
│   └── llm_explainer.py
│
├── data/
│   ├── games/
│   ├── training/
│   ├── benchmarks/
│   ├── openings/
│   ├── engine_matches/
│   └── networks/
│
└── docs/
    ├── architecture.md
    ├── evaluation.md
    ├── search.md
    └── learning.md
```

---

# 5. Board representation

## 5.1 Primary representation

Use **64-bit bitboards**.

A chessboard contains 64 squares, therefore one `uint64_t` can represent a set of squares.

Example:

```cpp
using Bitboard = std::uint64_t;
```

Maintain one bitboard per piece type and color:

```text
whitePawns
whiteKnights
whiteBishops
whiteRooks
whiteQueens
whiteKing

blackPawns
blackKnights
blackBishops
blackRooks
blackQueens
blackKing
```

Also maintain:

```text
whitePieces
blackPieces
occupied
```

These may be cached or computed from the individual piece bitboards.

---

## 5.2 Square indexing

Use a fixed square mapping:

```text
a1 = 0
b1 = 1
...
h1 = 7
a2 = 8
...
h8 = 63
```

This convention must remain consistent across:

- move generation
- attack tables
- FEN parsing
- hashing
- evaluation
- testing

---

## 5.3 Position state

Each position must contain at least:

```cpp
struct Position {
    Bitboard pieces[2][6];

    Color sideToMove;

    CastlingRights castlingRights;
    Square enPassantSquare;

    int halfmoveClock;
    int fullmoveNumber;

    std::uint64_t zobristKey;
};
```

Additional cached state may include:

```text
occupied
piecesByColor
king squares
material counts
pawn hash
incremental evaluation state
```

---

# 6. Move representation

Moves should be encoded compactly.

Recommended representation:

```cpp
using Move = std::uint32_t;
```

A move should contain enough information to represent:

- source square
- target square
- moving piece
- captured piece
- promotion piece
- capture flag
- en-passant flag
- castling flag
- double-pawn-push flag

Possible bit layout:

```text
bits  0-5   : from square
bits  6-11  : to square
bits 12-14  : promotion piece
bits 15-18  : flags
bits 19-21  : moving piece
bits 22-24  : captured piece
```

Exact encoding may change if benchmarking justifies it.

---

# 7. Move generation

The engine must generate:

- pawn pushes
- pawn double pushes
- pawn captures
- en passant
- knight moves
- bishop moves
- rook moves
- queen moves
- king moves
- kingside castling
- queenside castling
- promotions
- promotion captures

Two layers are recommended:

```text
pseudo-legal move generation
        ↓
legality filtering
```

Later, legality can be integrated directly for performance.

---

# 8. Attack generation

## Knights and kings

Use precomputed attack tables:

```cpp
Bitboard knightAttacks[64];
Bitboard kingAttacks[64];
```

## Pawns

Use separate tables by color:

```cpp
Bitboard pawnAttacks[2][64];
```

## Sliding pieces

Initial implementation may use ray scanning.

Optimized implementation should use one of:

- magic bitboards
- PEXT-based attack generation
- precomputed occupancy attack tables

Preferred long-term target: **magic bitboards or PEXT where supported**.

---

# 9. Move generation validation

Correct move generation is non-negotiable.

Use **PERFT** testing.

Example reference values from the standard starting position:

```text
Depth 1: 20
Depth 2: 400
Depth 3: 8,902
Depth 4: 197,281
Depth 5: 4,865,609
Depth 6: 119,060,324
```

The engine must pass:

- starting-position PERFT
- castling test positions
- en-passant positions
- promotion positions
- pinned-piece positions
- double-check positions
- discovered-check positions

No search work should begin until move generation is trustworthy.

---

# 10. Position hashing

Use **Zobrist hashing**.

Generate random 64-bit values for:

```text
piece × color × square
side to move
castling rights
en-passant file
```

Position key:

```text
hash =
    XOR(all pieces)
    XOR(side-to-move if black)
    XOR(castling state)
    XOR(en-passant state)
```

Zobrist keys are required for:

- transposition tables
- repetition detection
- pawn hash tables
- position caches

---

# 11. Make / unmake move

Search must avoid copying the entire board at every node.

Implement:

```cpp
void makeMove(Move move, StateInfo& state);
void unmakeMove(Move move, const StateInfo& state);
```

`StateInfo` stores everything required to restore the previous position.

Example:

```cpp
struct StateInfo {
    std::uint64_t previousZobrist;
    CastlingRights previousCastling;
    Square previousEnPassant;
    int previousHalfmoveClock;
    Piece capturedPiece;
};
```

Incrementally update:

- bitboards
- occupancy
- Zobrist key
- castling rights
- en-passant square
- clocks
- optional evaluation state

---

# 12. Search architecture

Initial search:

```text
Negamax
    +
Alpha-Beta pruning
```

Negamax simplifies minimax because chess is zero-sum.

Conceptual implementation:

```cpp
Score search(Position& pos, int depth, Score alpha, Score beta);
```

General rule:

```text
score(position for us)
=
-score(position for opponent)
```

---

# 13. Search score convention

Use integer scores internally.

Recommended:

```text
1 pawn = 100 centipawns
```

Example:

```text
+25  = +0.25
+100 = +1.00
-350 = -3.50
```

Define explicit constants:

```cpp
constexpr Score SCORE_DRAW = 0;
constexpr Score SCORE_MATE = 32000;
constexpr Score SCORE_INF  = 32767;
```

Mate scores should encode distance:

```text
mate sooner > mate later
being mated later > being mated sooner
```

Example:

```cpp
SCORE_MATE - ply
```

---

# 14. Search v1

First working search must support:

- negamax
- alpha-beta
- terminal detection
- fixed depth
- principal variation reconstruction
- node counter

Pseudo-code:

```text
search(position, depth, alpha, beta):

    if terminal:
        return terminal_score

    if depth == 0:
        return evaluate(position)

    best = -infinity

    for move in legal_moves:
        make(move)

        score = -search(
            child,
            depth - 1,
            -beta,
            -alpha
        )

        unmake(move)

        best = max(best, score)
        alpha = max(alpha, score)

        if alpha >= beta:
            break

    return best
```

---

# 15. Iterative deepening

Do not search directly to depth N.

Search progressively:

```text
depth 1
depth 2
depth 3
...
depth N
```

Advantages:

- better move ordering
- usable best move if time expires
- principal variation at every depth
- more stable time management

---

# 16. Principal variation

The engine must store the best known line.

Example:

```text
depth 15
score +0.41
pv e2e4 e7e5 g1f3 b8c6 f1b5
```

The principal variation is needed for:

- UCI output
- analysis mode
- debugging
- move explanation

---

# 17. Transposition table

Use a fixed-size hash table.

Suggested entry:

```cpp
struct TTEntry {
    std::uint64_t key;
    Move bestMove;
    Score score;
    std::int16_t depth;
    Bound bound;
    std::uint8_t age;
};
```

Bounds:

```text
EXACT
LOWER_BOUND
UPPER_BOUND
```

A TT hit may:

- return a result immediately
- tighten alpha/beta
- provide the first move for ordering

Replacement strategy may initially be:

```text
replace if:
- empty
- same key
- greater/equal depth
- older generation
```

Later benchmarking can improve it.

---

# 18. Move ordering

Recommended ordering:

```text
1. TT move
2. winning captures
3. promotions
4. killer moves
5. history heuristic moves
6. quiet moves
7. losing captures
```

Capture ordering can initially use:

**MVV-LVA**

Most Valuable Victim / Least Valuable Attacker.

Later replace or supplement with:

- Static Exchange Evaluation
- capture history

Good move ordering is essential for effective alpha-beta pruning.

---

# 19. Quiescence search

At nominal depth zero, do not immediately call static evaluation.

Run a quiescence search over tactically unstable moves.

Initial quiescence move set:

- captures
- promotions
- legal evasions when in check

Possible later additions:

- selected checking moves

Pseudo-flow:

```text
qsearch(position, alpha, beta)

    stand_pat = evaluate(position)

    if stand_pat >= beta:
        return beta

    alpha = max(alpha, stand_pat)

    for tactical move:
        search capture continuation
```

Purpose: reduce the horizon effect.

---

# 20. Search improvements roadmap

Add only after the basic search is stable.

Recommended order:

1. transposition table
2. move ordering
3. quiescence search
4. killer heuristic
5. history heuristic
6. aspiration windows
7. null-move pruning
8. late move reductions
9. futility pruning
10. razoring
11. check extensions
12. singular extensions
13. static exchange evaluation
14. internal iterative reductions
15. multi-threaded search

Every optimization must be validated through automated engine matches.

---

# 21. Static evaluation v1

The first evaluator must be **handcrafted and explainable**.

General form:

```text
Evaluation =
    material
  + piece_square
  + mobility
  + pawn_structure
  + passed_pawns
  + bishop_pair
  + rook_activity
  + king_safety
  + space
  + tempo
```

Return score from the side-to-move convention chosen by the engine.

---

# 22. Material evaluation

Starting values:

```text
Pawn   = 100
Knight = 320
Bishop = 330
Rook   = 500
Queen  = 900
King   = non-material
```

These are initial values only.

Later they may be tuned automatically.

---

# 23. Piece-square tables

Use Piece-Square Tables for each piece.

At minimum distinguish:

- middlegame values
- endgame values

Example:

```text
knight on center square > knight on rim
king centralization bad in middlegame
king centralization useful in endgame
```

Evaluation should interpolate between game phases.

---

# 24. Game phase interpolation

Use a phase score derived from remaining material.

Example weights:

```text
Knight = 1
Bishop = 1
Rook   = 2
Queen  = 4
```

Maximum phase for normal initial material:

```text
24
```

Blend:

```text
final_score =
    mg_score * phase
  + eg_score * (MAX_PHASE - phase)
```

normalized by `MAX_PHASE`.

This allows one evaluation feature to behave differently in middlegames and endgames.

---

# 25. Pawn structure evaluation

Detect at minimum:

- doubled pawns
- isolated pawns
- backward pawns
- pawn islands
- connected pawns
- passed pawns
- protected passed pawns
- candidate passed pawns

Pawn structure should eventually use its own pawn hash because it changes less frequently than full board positions.

---

# 26. Passed pawns

Passed-pawn bonuses should scale by rank.

Example:

```text
2nd rank: small bonus
3rd rank: small bonus
4th rank: moderate
5th rank: larger
6th rank: high
7th rank: very high
```

Additional terms:

- supported passed pawn
- connected passed pawn
- blocked passed pawn
- king distance
- enemy rook behind pawn
- own rook behind pawn

---

# 27. Mobility

Measure legal or pseudo-legal activity of pieces.

Example:

```text
bishop mobility
rook mobility
queen mobility
knight mobility
```

Mobility should avoid rewarding moves into attacked or unusable squares without adjustment.

---

# 28. King safety

Initial features:

- pawn shield
- open files near king
- semi-open files near king
- enemy queen presence
- attackers near king
- attacked squares in king zone
- castling state
- exposed king
- unsafe diagonals/files

King safety must decrease in importance as the position enters the endgame.

---

# 29. Additional positional features

Later handcrafted evaluation may include:

- bishop pair
- bad bishop
- outposts
- rook on open file
- rook on semi-open file
- rook on seventh rank
- connected rooks
- trapped pieces
- weak squares
- space advantage
- center control
- threats
- hanging pieces
- king opposition
- endgame king activity

---

# 30. Explainable evaluation

The evaluator must optionally provide a breakdown.

API example:

```cpp
struct EvalBreakdown {
    int material;
    int pieceSquare;
    int mobility;
    int pawnStructure;
    int passedPawns;
    int bishopPair;
    int rookActivity;
    int kingSafety;
    int space;
    int tempo;
    int total;
};
```

Example output:

```text
Material:           +0.00
Piece placement:    +0.22
Mobility:           +0.14
Pawn structure:     -0.08
Passed pawns:       +0.31
King safety:        +0.41
Space:              +0.17
Tempo:              +0.10
--------------------------------
Static evaluation:  +1.27
```

Important:

The **static evaluation** and the **searched evaluation** are different values.

Example:

```text
Static eval: +0.30
Search depth 18: +1.12
```

The analysis UI should expose both.

---

# 31. Time management

The engine must support:

```text
fixed depth
fixed node count
fixed move time
full clock
increment
moves to go
infinite analysis
```

UCI examples:

```text
go depth 12
go nodes 1000000
go movetime 5000
go wtime 120000 btime 120000 winc 1000 binc 1000
```

The search must be interruptible.

Use an atomic stop flag.

---

# 32. UCI protocol

Implement the Universal Chess Interface.

Minimum commands:

```text
uci
isready
ucinewgame
position startpos
position fen ...
go
stop
quit
setoption
```

Minimum output:

```text
id name <engine-name>
id author <author>
uciok
readyok
bestmove <move>
```

Recommended engine options:

```text
Hash
Threads
OwnBook
BookFile
BookPolicy
MultiPV
AnalysisDetail
NNUE
NNUEFile
```

Analysis output:

```text
info depth 18
     seldepth 27
     score cp 42
     nodes 823443
     nps 1500000
     time 549
     pv e2e4 e7e5 g1f3 ...
```

---

# 33. PGN support

PGN parsing can initially live in Python tooling.

The system should support:

- importing games
- replaying games
- evaluating every position
- generating move-by-move reports
- exporting annotated PGN

Example annotation:

```text
12.Nf3 {+0.35 -> -0.62, mistake}
```

---

# 34. Game analysis

For every played move:

1. evaluate current position
2. calculate best engine move
3. evaluate played move
4. compute loss

Define:

```text
evaluation_loss =
best_move_score - played_move_score
```

Classification thresholds should be configurable.

Initial example:

```text
0–20 cp      = best/excellent
20–50 cp     = good
50–100 cp    = inaccuracy
100–250 cp   = mistake
>250 cp      = blunder
```

These values are placeholders and should eventually account for:

- position complexity
- mate transitions
- winning/losing states
- practical impact

---

# 35. Analysis output

Each move may store:

```json
{
  "ply": 31,
  "move": "Nf3",
  "best_move": "Re1",
  "score_before": 34,
  "score_after": -62,
  "loss_cp": 96,
  "depth": 18,
  "nodes": 2184421,
  "classification": "inaccuracy",
  "pv": ["Re1", "Qd7", "Nf1", "Rad8"]
}
```

---

# 36. Game database

Store self-play and analysis games.

Recommended initial format:

```text
PGN + JSON metadata
```

Metadata:

```text
engine version
git commit
evaluation version
search parameters
time control
random seed
opening source
result
termination reason
hardware
nodes searched
average depth
```

For large-scale training, migrate to a compact binary dataset.

---

# 37. Determinism

The engine must support deterministic mode.

With:

```text
same executable
same position
same parameters
same node limit
same thread count
same random seed
```

it should produce the same result.

This is important for:

- debugging
- regression testing
- scientific comparison

---

# 38. Logging

Configurable logging levels:

```text
OFF
ERROR
INFO
DEBUG
TRACE
```

Possible debug output:

```text
position key
generated moves
search tree samples
TT hits
cutoffs
evaluation breakdown
principal variation
node types
```

Logging must be disabled or cheap during performance benchmarks.

---

# 39. Engine benchmarking

Create a built-in benchmark command.

The benchmark should use a fixed suite of positions.

Record:

```text
total nodes
elapsed time
nodes per second
depth
score
best move
TT hit rate
beta cutoffs
qsearch nodes
```

This detects performance regressions.

---

# 40. Strength testing

Never judge a search optimization from a few sample games.

Automate engine-versus-engine matches.

Compare:

```text
new version
vs
previous baseline
```

Use:

- same openings
- colors reversed
- many games
- fixed time control

Track:

```text
wins
draws
losses
score percentage
Elo estimate
confidence interval
```

Recommended later tooling:

- SPRT testing
- cutechess-cli

---

# 41. Testing strategy

## Unit tests

Test:

- square mapping
- bit operations
- attack maps
- move encoding
- FEN parsing
- FEN serialization
- make/unmake
- Zobrist consistency
- castling rights
- en passant
- promotions

## Search tests

Known tactical positions:

```text
mate in 1
mate in 2
winning queen
avoid hanging queen
forced recapture
stalemate
repetition
```

## Regression tests

Maintain a position suite where every engine release records:

```text
best move
score
depth
nodes
PV
```

Unexpected changes become inspectable.

---

# 42. FEN support

Must support full FEN:

```text
piece placement
side to move
castling rights
en passant
halfmove clock
fullmove number
```

Example:

```text
rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
```

---

# 43. Draw detection

Implement:

- stalemate
- threefold repetition
- fifty-move rule
- insufficient material

For search, repetition history must include previous Zobrist keys.

Search may treat claimable draws according to engine design, but the behavior must be explicit and tested.

---

# 44. Engine match and self-play subsystem

The project must include a general match orchestrator capable of running:

```text
our engine vs itself
our engine vs Stockfish
our engine vs another local UCI engine
our engine vs a friend's engine
new version vs previous version
network A vs network B
```

The preferred interoperability standard is **UCI**.

Any external engine that correctly implements UCI should be usable without modifying the core engine.

Example:

```bash
python tools/match_runner.py \
    --engine-a ./our_engine \
    --engine-b ./stockfish \
    --games 100 \
    --time 60+0.6 \
    --output data/engine_matches/
```

Self-play is simply a special case where both engine paths or configurations point to our engine.

The runner must support separate configuration for each side:

```text
engine executable
engine name
engine version
UCI options
Hash
Threads
network/evaluator
working directory
environment
```

The match subsystem must capture:

```text
result
termination reason
PGN
final FEN
engine versions
UCI options
time control
opening/forced-line identifier
random seed
per-move clock usage
evaluations where available
```

The orchestrator must not assume that the opponent exposes internal evaluation details.

---

# 45. Match start modes

Every engine-vs-engine match must support several independent start modes.

## 45.1 Free game from move 1

```text
startpos
```

Both engines calculate from the initial position.

No opening moves are forced.

This is required for testing the engine's complete behavior from move 1.

## 45.2 Arbitrary position

The user may supply any legal FEN.

Example:

```bash
python tools/match_runner.py \
    --engine-a ./our_engine \
    --engine-b ./stockfish \
    --fen "..." \
    --games 20
```

The engines begin calculating immediately from that position.

Use cases:

- middlegame training
- endgame training
- tactical positions
- testing a known weakness
- reproducing a game position

## 45.3 Forced move prefix

The user may supply an exact sequence of legal moves.

Example:

```text
1.d4 Nf6
2.c4 g6
3.Nc3 d5
```

The runner applies those moves without engine choice.

Once the forced prefix ends:

```text
both engines are released
and calculate normally
```

This allows exact variation training.

## 45.4 Named opening or opening family

The runner must be able to start games from an opening suite.

Examples:

```text
Grünfeld Defence
Italian Game
Queen's Gambit
Sicilian Defence
French Defence
```

Named openings must map to one or more reproducible move prefixes or FEN positions in the project's opening database.

A named opening must never be treated as a vague natural-language instruction during actual engine testing.

It must resolve to:

```text
opening ID
ECO code where available
canonical move sequence or position set
variation identifier
```

## 45.5 Exact variation

The user may request a precise sub-variation.

Example:

```text
Grünfeld Defence
Exchange Variation
specific line supplied by PGN/UCI moves
```

The runner forces the full requested prefix and then releases both engines.

---

# 46. Opening-side and color control

Opening tests must support:

```text
our engine always White
our engine always Black
alternate colors
paired games with reversed colors
```

For serious engine comparison, default to paired games:

```text
Game 1:
Engine A = White
Engine B = Black

Game 2:
Engine B = White
Engine A = Black
```

using the same starting line/position.

This reduces opening and color bias.

---

# 47. Opening source formats

Opening suites should support:

```text
PGN
EPD
FEN lists
UCI move lists
Polyglot-compatible book data
project-native opening database
```

Each opening entry should be identifiable.

Suggested structure:

```json
{
  "id": "gruenfeld_exchange_001",
  "name": "Grünfeld Defence: Exchange Variation",
  "eco": "D85",
  "start_fen": "startpos",
  "moves_uci": [
    "d2d4",
    "g8f6",
    "c2c4",
    "g7g6",
    "b1c3",
    "d7d5"
  ]
}
```

PGN/SAN may be used for human input, but match execution should normalize to a deterministic internal representation such as UCI moves plus start FEN.

---

# 48. Opening book and opening database modes

The engine must support at least two clearly separated opening modes.

## Mode A — Think from move 1

```text
OwnBook = false
```

The engine performs normal search from the initial position.

No move is selected from an opening database.

This is the default mode for measuring the engine's true search/evaluation behavior from move 1.

## Mode B — Use own opening database

```text
OwnBook = true
```

Before searching, the engine checks whether the current position exists in its opening database.

If a book move is available, the engine may select it according to a configurable policy.

Possible policies:

```text
best statistical move
weighted random
highest engine score
most played
highest win rate
training/exploration policy
```

Once the current position is no longer in the database:

```text
normal search begins
```

The engine's own book must be optional and must never be required for legal play.

---

# 49. Opening database schema

A book entry may contain:

```text
position key
FEN
candidate moves
number of games
wins
draws
losses
score percentage
source
engine evaluation
learned preference
last update
```

Example:

```json
{
  "zobrist": "0x...",
  "fen": "...",
  "moves": [
    {
      "move": "g8f6",
      "games": 18240,
      "wins": 6120,
      "draws": 8010,
      "losses": 4110,
      "engine_score_cp": 22,
      "weight": 0.71
    }
  ]
}
```

The book database should be versioned separately from the search engine.

---

# 50. Opening training modes

The match runner should support specific training workflows.

Examples:

```text
train only Grünfeld positions
train only one exact Grünfeld line
train positions after move 10
play both sides of the same line
repeat a losing position against stronger engines
sample random positions from an opening family
```

A training job may specify:

```text
opening
variation
forced plies
release ply
side to train
opponent
number of games
time control
book enabled/disabled
```

Example conceptual configuration:

```yaml
opening: "Grünfeld Defence"
variation: "Exchange Variation"
forced_plies: 16
side_to_train: black
opponent: stockfish
games: 200
own_book: false
```

---

# 51. Avoiding self-play collapse

Pure deterministic self-play can repeatedly generate identical games.

Introduce controlled diversity through one or more of:

- randomized opening positions
- opening books used only for diversity
- limited weighted move selection in early moves
- multiple engine snapshots
- randomized seeds where appropriate

Do not randomize evaluation during serious strength testing.

---

# 46. Learning roadmap

Learning is divided into separate stages.

## Stage A — manual evaluation

Handcrafted features.

Goal:

- interpretability
- debugging
- baseline engine

## Stage B — automated parameter tuning

Keep the feature structure but learn weights.

Examples:

```text
pawn value
bishop pair bonus
mobility weights
passed pawn bonus
king safety penalties
```

Possible methods:

- Texel tuning
- gradient-based optimization
- coordinate descent
- evolutionary strategies

## Stage C — learned evaluator

Train a neural evaluator from positions and outcomes.

## Stage D — NNUE-style incremental network

Integrate a network optimized for CPU inference.

## Stage E — reinforcement/self-play improvement

Generate new training data using the engine itself.

---

# 47. Texel-style tuning

Dataset:

```text
position
evaluation features
game result
```

Game result:

```text
white win = 1.0
draw      = 0.5
black win = 0.0
```

Optimize evaluation weights to minimize prediction error between engine evaluation and game outcome.

Do not blindly train on low-quality positions.

Potential filtering:

- remove opening book positions
- remove trivial mates
- deduplicate positions
- balance evaluation ranges
- avoid excessive correlated samples from the same game

---

# 48. Neural evaluation

The network should initially only replace or supplement static evaluation.

Search remains alpha-beta.

Input candidates:

- piece-square occupancy
- side to move
- king squares
- castling rights
- optional handcrafted features

Output:

```text
single scalar position score
```

Possible output representations:

```text
centipawn-like score
expected result
WDL probabilities
```

WDL:

```text
P(win)
P(draw)
P(loss)
```

---

# 49. NNUE target architecture

Long-term learned evaluator should be efficient enough for millions of evaluations.

Conceptual design:

```text
board features
    ↓
incrementally updatable accumulator
    ↓
small hidden network
    ↓
position score
```

Do not implement NNUE before:

- move generation is correct
- search works
- handcrafted evaluator exists
- benchmark infrastructure exists
- training pipeline exists

---

# 50. Training labels

Possible labels:

## Search teacher labels

```text
position → deep engine evaluation
```

Useful for supervised learning.

## Game result labels

```text
position → W/D/L
```

Useful for outcome prediction.

## Mixed targets

Combine:

```text
deep search evaluation
+
eventual game result
```

This can reduce noise.

---

# 51. Experience storage

The engine should not directly modify itself after every individual game.

Instead:

```text
play games
    ↓
collect data
    ↓
filter data
    ↓
train candidate
    ↓
benchmark candidate
    ↓
engine match
    ↓
accept/reject
```

This prevents catastrophic degradation.

Every trained model must be versioned.

---

# 52. Model promotion rule

A candidate network or parameter set becomes the default only if it passes:

```text
correctness tests
performance benchmark
tactical suite
self-play strength test
regression suite
```

No automatic production promotion solely because training loss decreased.

---

# 53. Versioning

Version separately:

```text
engine binary
search version
evaluation version
network version
training dataset version
```

Example:

```text
engine:      0.6.0
search:      s14
eval:        hce-07
network:     nnue-0018
dataset:     selfplay-2026-09-v3
```

---

# 54. Reproducible experiments

Every experiment should store:

```json
{
  "engine_commit": "...",
  "network": "...",
  "dataset": "...",
  "seed": 12345,
  "threads": 1,
  "hash_mb": 256,
  "time_control": "10+0.1",
  "compiler": "...",
  "compiler_flags": "...",
  "cpu": "..."
}
```

---

# 55. Performance targets

Do not impose unrealistic strength targets initially.

Engineering milestones:

## Milestone 1

```text
legal chess
PERFT correct
```

## Milestone 2

```text
basic alpha-beta search
simple material evaluation
```

## Milestone 3

```text
100k+ nodes/s in optimized build
```

## Milestone 4

```text
transposition tables
quiescence
move ordering
```

## Milestone 5

```text
1M+ nodes/s target on modern desktop hardware
```

Exact NPS depends strongly on architecture and evaluation complexity.

Strength matters more than raw NPS.

---

# 56. Compiler configuration

Development:

```text
-Wall
-Wextra
-Wpedantic
sanitizers
debug symbols
```

Release:

```text
-O3
-march=native
NDEBUG
LTO where useful
```

Use:

- AddressSanitizer
- UndefinedBehaviorSanitizer

during development.

---

# 57. Multithreading

Do not implement early.

First target:

```text
single-threaded deterministic engine
```

Later use Lazy SMP or another parallel search design.

Thread-shared resources may include:

```text
transposition table
stop flag
time manager
```

Each search thread may maintain:

```text
history table
killer moves
search stack
local node count
```

Parallel scaling must be measured, not assumed.

---

# 58. Memory model

Important configurable engine options:

```text
Hash
Threads
Move Overhead
NNUE network path
analysis mode
```

Example UCI options:

```text
setoption name Hash value 512
setoption name Threads value 8
```

---

# 59. Search stack

Maintain per-ply state.

Example:

```cpp
struct SearchStack {
    Move currentMove;
    Move killers[2];
    int staticEval;
    int ply;
};
```

Avoid unnecessary allocation inside the search loop.

---

# 60. Static Exchange Evaluation

Implement SEE later to estimate tactical capture sequences without full search.

Useful for:

- capture ordering
- pruning bad captures
- quiescence search

Concept:

```text
If I capture this piece,
and opponent recaptures,
and I recapture...
what is the net material result?
```

---

# 61. Null move pruning

Idea:

```text
If I could pass my turn and still remain >= beta,
the real position is probably strong enough for cutoff.
```

Restrictions needed for:

- check
- zugzwang-like endgames
- low-material positions

Implementation only after baseline search is tested.

---

# 62. Late Move Reductions

Moves searched late in a well-ordered move list are statistically less likely to be best.

Search them initially at reduced depth.

If they exceed alpha, re-search at full depth.

Never blindly reduce:

- tactical moves
- checks
- principal variation moves
- critical positions

Exact conditions require tuning.

---

# 63. Aspiration windows

After completing depth N, use its score to search depth N+1 with a narrow alpha-beta window.

Example:

```text
previous score = +35 cp

search window:
alpha = +15
beta  = +55
```

If search fails low/high, widen and repeat.

---

# 64. Search node types

Useful conceptual node types:

```text
PV node
cut node
all node
```

This becomes relevant for:

- reductions
- extensions
- pruning
- debugging search behavior

---

# 65. Opening handling inside the engine

Core engine must not depend on an opening book.

Opening behavior must be explicitly selectable:

```text
OwnBook = false
→ calculate from the current position, including move 1

OwnBook = true
→ query the engine's own opening database first
→ search normally when no usable book entry exists
```

The engine must expose book use through UCI options.

Example:

```text
option name OwnBook type check default false
option name BookFile type string default
option name BookPolicy type combo default weighted
```

Possible `BookPolicy` values:

```text
best
weighted
random
explore
```

Book formats may include:

- project-native database
- Polyglot
- imported PGN-derived book

The book subsystem must return metadata explaining why a move was selected.

Example:

```text
book move: d2d4
policy: weighted
games: 18,240
weight: 0.71
```

When benchmarking search strength, every report must explicitly state:

```text
book enabled/disabled
book version
forced opening prefix
release ply
```

A forced match opening and the engine's own opening book are separate concepts.

Example:

```text
runner forces Grünfeld moves until ply 12
then engines are released

after release:
Engine A may use its own book
Engine B may use its own book
or either/both may calculate immediately
```

---

# 66. Endgame tablebases

Later integrate Syzygy tablebases.

Use for exact positions with supported piece counts.

Possible outputs:

```text
WDL
DTZ
```

Tablebases must remain optional.

The engine must still function without them.

---

# 67. Analysis mode

Analysis mode should expose:

```text
best move
searched score
static score
depth
seldepth
nodes
NPS
hash usage
principal variation
evaluation breakdown
candidate alternatives
opening identification
book status
```

The user must be able to enable a detailed evaluation view.

Example:

```text
Position evaluation: +0.91
Static evaluation:   +0.47
Search depth:        19

Material:            +0.00
Piece activity/PST:  +0.18
Mobility:            +0.14
Pawn structure:      -0.09
Passed pawns:        +0.00
Bishop pair:         +0.20
Rook activity:       +0.00
King safety:         +0.38
Space:               +0.10
Tempo:               +0.06
```

The detailed view should be available for:

```text
current position
position before a move
position after a move
each move of a full PGN analysis
each MultiPV candidate where practical
```

MultiPV example:

```text
1. c5   +0.91
2. Bg7  +0.55
3. e6   +0.42
```

For every candidate, the UI/tooling should be able to request:

```text
PV
static breakdown
searched score
difference from best move
```

Analysis mode should expose structured JSON in addition to human-readable text so the local LLM layer can consume the data reliably.

---

# 68. Explanation layer

The engine's explanation system must clearly distinguish:

```text
static reasons
vs
search consequences
```

Example:

```text
Static:
+0.40 king safety
+0.22 activity
-0.15 pawn structure

Search:
18...Bxh2+ fails because of
19.Kxh2 Qh4+ 20.Kg1

Final search evaluation: +1.42
```

The analysis subsystem must expose the individual evaluation components at every requested position.

At minimum:

```text
total static evaluation
searched evaluation
material
piece-square/activity
mobility
pawn structure
passed pawns
bishop pair
rook activity
king safety
space
tempo
game phase
principal variation
best move
candidate moves
```

Example machine-readable payload:

```json
{
  "fen": "...",
  "side_to_move": "black",
  "static_eval_cp": 47,
  "search_eval_cp": 91,
  "depth": 19,
  "evaluation": {
    "material": 0,
    "piece_square": 18,
    "mobility": 14,
    "pawn_structure": -9,
    "passed_pawns": 0,
    "bishop_pair": 20,
    "rook_activity": 0,
    "king_safety": 38,
    "space": 10,
    "tempo": 6
  },
  "best_move": "c7c5",
  "pv": ["c7c5", "d4c5", "d8a5"]
}
```

This structured output is the canonical source for explanations.

---

# 69. Move explanation and local LLM assistant

High-level explanations can combine:

```text
evaluation delta
principal variation
feature changes
tactical motifs
candidate comparison
```

Example:

```text
Move: 18.Bxh7?

Why it fails:
- bishop is sacrificed for insufficient compensation
- king attack does not lead to a forced continuation
- after 18...Kxh7 the material balance changes by -3.0
- search finds no adequate follow-up

Evaluation:
before: +0.20
after:  -2.65
```

Natural-language generation must be downstream from engine calculations, not a replacement for them.

---

## 69.1 Local LLM assistant

The project must optionally support a **small local LLM** for interactive questions about the current position or analysis.

Possible local runtimes:

```text
llama.cpp
Ollama
another local inference server
```

The exact model/runtime must remain replaceable.

The chess engine itself remains the source of chess calculations.

The LLM must never be treated as the authoritative evaluator.

Architecture:

```text
board position
      │
      ├──► chess engine
      │       │
      │       ├── static evaluation breakdown
      │       ├── searched evaluation
      │       ├── principal variation
      │       ├── candidate moves
      │       └── tactical/search metadata
      │
      ▼
structured analysis context
      │
      ▼
local LLM
      │
      ▼
natural-language explanation / Q&A
```

---

## 69.2 Questions supported by the LLM layer

Examples:

```text
Why does the engine prefer c5 here?
Why is White +1.2 if material is equal?
What is wrong with Bxh7+?
Why did the evaluation change from +0.3 to -1.8?
Which piece is badly placed?
Is my king unsafe?
What should Black's plan be?
Why does the engine prefer this rook trade?
What happens if I play Qd2 instead?
```

The LLM receives structured engine data relevant to the question.

It should not calculate arbitrary tactical truth independently when the engine can provide it.

---

## 69.3 LLM grounding context

A position explanation request should be able to include:

```text
FEN
side to move
move being discussed
previous position if relevant
static evaluation
search evaluation
evaluation component breakdown
best move
MultiPV candidates
principal variation
material balance
piece locations
attack/defense maps where available
detected pawn features
king-safety features
tactical motifs detected by engine/tooling
game history
opening identification
```

For a move comparison, provide both before/after feature deltas.

Example:

```json
{
  "question": "Why is Nf3 better than f3?",
  "position": {"fen": "..."},
  "engine": {
    "best_move": "g1f3",
    "best_score_cp": 36,
    "alternatives": [
      {"move": "f2f3", "score_cp": -22}
    ]
  },
  "feature_delta": {
    "g1f3": {
      "mobility": 18,
      "king_safety": 4,
      "development": 20
    },
    "f2f3": {
      "mobility": 2,
      "king_safety": -31,
      "development": 0
    }
  },
  "pv": ["g1f3", "g8f6", "c2c4"]
}
```

---

## 69.4 LLM anti-hallucination requirements

The prompt/system contract for the local LLM must require:

- do not invent engine scores
- do not invent principal variations
- distinguish facts supplied by the engine from interpretation
- state when the engine data is insufficient
- avoid claiming a tactic is forced unless search data supports it
- cite the relevant evaluation components in its explanation
- keep score perspective consistent
- distinguish static evaluation from searched evaluation

If the user asks a chess question requiring calculation not already present in context:

```text
LLM requests more engine analysis
→ engine computes it
→ result is returned to LLM
→ LLM explains it
```

The LLM must not silently substitute its own chess intuition for missing engine calculation.

---

## 69.5 Local-only mode

The assistant layer must support a fully local configuration:

```text
chess engine: local
LLM: local
game database: local
analysis history: local
```

No cloud service should be required for core analysis or explanation.

---

## 69.6 LLM interface

Define an adapter rather than hard-coding one provider.

Conceptual interface:

```python
class ChessExplainer:
    def explain_position(self, context, question):
        ...

    def explain_move(self, context, move, question=None):
        ...

    def compare_moves(self, context, moves, question=None):
        ...
```

Possible implementations:

```text
OllamaExplainer
LlamaCppExplainer
NoLLMExplainer
```

This keeps the chess engine independent from the language model.

---

# 70. Engine API

Core engine should expose a clean interface.

Example:

```cpp
struct SearchLimits {
    int depth = 0;
    std::uint64_t nodes = 0;
    int moveTimeMs = 0;
    bool infinite = false;
};

struct SearchResult {
    Move bestMove;
    Move ponderMove;
    Score score;
    int depth;
    int selectiveDepth;
    std::uint64_t nodes;
    std::vector<Move> principalVariation;
};

class Engine {
public:
    void setPosition(const Position&);
    SearchResult search(const SearchLimits&);
    EvalBreakdown evaluateDetailed() const;
    void stop();
};
```

---

# 71. Python integration

Possible options:

## subprocess + UCI

Preferred initially.

Python launches engine binary and communicates over stdin/stdout.

Advantages:

- simple
- standard
- isolated
- compatible with external tools

## bindings

Later:

- pybind11

Useful for:

- high-throughput data generation
- direct evaluator access
- feature extraction

Do not introduce bindings before UCI is stable.

---

# 72. Data formats

## Positions

Use FEN for human-readable interchange.

## Games

Use PGN.

## Training data

Initial:

```text
CSV / Parquet
```

Large scale:

```text
custom binary shards
```

Suggested training row:

```text
zobrist
FEN
side_to_move
features
search_score
WDL
game_result
ply
engine_version
```

Avoid storing redundant textual FEN at very large scale unless needed.

---

# 73. Evaluation normalization

Internal search evaluation should use centipawns.

When showing a human-readable score:

```text
score_cp / 100.0
```

Neural models may use bounded targets.

Possible transformation:

```text
cp → win probability
```

using a logistic function.

Calibration must be learned from data rather than assumed universal.

---

# 74. Checkmate reporting

Internally:

```text
SCORE_MATE - ply
```

Externally:

```text
mate 3
mate -5
```

Do not show a mate as an arbitrary `+999.0`.

---

# 75. Error handling

The engine must reject or clearly report:

- invalid FEN
- illegal moves
- malformed UCI commands
- unsupported options
- impossible position state

Debug builds should assert invariants aggressively.

Release builds should avoid crashing on user input.

---

# 76. Board invariants

Useful debug assertions:

```text
exactly one king per side
no square contains two pieces
occupied == whitePieces | blackPieces
whitePieces & blackPieces == 0
king square matches king bitboard
Zobrist key matches recomputed hash
```

---

# 77. Testing make/unmake

Critical invariant:

```text
position_before
→ make(move)
→ unmake(move)
== position_before
```

Validate:

- board
- side to move
- clocks
- castling rights
- en passant
- Zobrist
- incremental eval state

Perform randomized stress tests over many legal games.

---

# 78. Continuous integration

CI should run:

```text
build
unit tests
PERFT suite
sanitizer tests
small benchmark
format/lint checks
```

Do not run massive engine matches on every commit.

Run long strength tests separately.

---

# 79. Code quality principles

Prefer:

- explicit state
- deterministic behavior
- no hidden global mutable state where avoidable
- no allocation in inner search loops
- measurable optimizations
- tests before micro-optimization
- comments explaining chess-engine logic, not obvious syntax

Every search optimization should have:

```text
reason
expected effect
benchmark
strength result
```

---

# 80. Development phases

## Phase 0 — Skeleton

Deliverables:

- CMake project
- CLI executable
- test framework
- board constants
- basic types

## Phase 1 — Chess rules

Deliverables:

- FEN
- board representation
- moves
- move generation
- make/unmake
- legality
- PERFT

Exit criterion:

```text
all PERFT tests pass
```

## Phase 2 — First engine

Deliverables:

- material evaluation
- negamax
- alpha-beta
- terminal positions
- best move output

Exit criterion:

```text
engine plays complete legal games
```

## Phase 3 — Real search

Deliverables:

- iterative deepening
- quiescence
- TT
- move ordering
- time management
- UCI

Exit criterion:

```text
usable from a chess GUI
```

## Phase 4 — Positional evaluation

Deliverables:

- tapered eval
- PSTs
- pawns
- mobility
- king safety
- passed pawns
- explanation breakdown

Exit criterion:

```text
evaluation is both stronger and interpretable
```

## Phase 5 — Search optimization

Deliverables:

- SEE
- killers
- history
- null move
- LMR
- aspiration windows
- extensions/pruning

Exit criterion:

```text
measurable Elo increase over Phase 4
```

## Phase 6 — Analysis system

Deliverables:

- PGN analyzer
- move classifications
- MultiPV
- full evaluation-component breakdown
- structured JSON analysis output
- annotated output
- explanation context generation
- optional local LLM Q&A layer

## Phase 7 — Engine matches, openings, and self-play

Deliverables:

- generic UCI match runner
- our engine vs Stockfish/external engines
- arbitrary FEN start positions
- exact forced move prefixes
- named opening suites
- exact variation training
- paired color-reversed games
- own-book enabled/disabled modes
- game storage
- automatic version comparison
- experiment metadata

## Phase 8 — Evaluation tuning

Deliverables:

- dataset generation
- parameter tuner
- candidate evaluation
- automatic accept/reject workflow

## Phase 9 — Neural evaluation

Deliverables:

- training pipeline
- neural evaluator
- C++ inference
- engine-vs-engine validation

## Phase 10 — Continuous learning loop

Deliverables:

```text
self-play
→ dataset
→ training
→ candidate
→ testing
→ promotion
```

---

# 81. First minimum viable engine

The first usable version should contain only:

```text
bitboard board
legal move generation
make/unmake
FEN
PERFT
material evaluation
piece-square tables
negamax
alpha-beta
iterative deepening
quiescence
simple move ordering
UCI
```

Do not add machine learning before this version works correctly.

---

# 82. Suggested initial engine configuration

```text
Threads: 1
Hash: 64 MB
Evaluation: handcrafted
Search: alpha-beta negamax
Max ply: 128
UCI: enabled
NNUE: disabled
Tablebases: disabled
Opening book: disabled
```

---

# 83. Core performance metrics

Track continuously:

```text
NPS
average depth
selective depth
TT hit rate
beta cutoff rate
first-move cutoff rate
qsearch percentage
branching factor
memory usage
```

Strength metrics:

```text
Elo vs baseline
tactical-suite accuracy
game score
W/D/L
```

Training metrics:

```text
dataset size
validation loss
WDL calibration
engine Elo after integration
```

---

# 84. Design rule for improvements

An engine modification is considered successful only if it improves at least one of:

```text
correctness
playing strength
analysis quality
speed
memory usage
explainability
```

without causing an unacceptable regression elsewhere.

A lower neural-network loss alone does not prove that the chess engine improved.

A higher NPS alone does not prove that the chess engine improved.

The definitive measurement for playing changes is **engine-versus-engine testing**.

---

# 85. Long-term target architecture

```text
                         ┌─────────────────┐
                         │      UCI/UI     │
                         └────────┬────────┘
                                  │
                           position / go
                                  │
                         ┌────────▼────────┐
                         │     ENGINE      │
                         └────────┬────────┘
                                  │
                  ┌───────────────┴──────────────┐
                  │                              │
          ┌───────▼────────┐             ┌──────▼───────┐
          │     SEARCH     │             │  EVALUATION  │
          │                │             │              │
          │ Alpha-Beta     │             │ HCE / NNUE   │
          │ TT             │             │ Explainable  │
          │ LMR            │             └──────┬───────┘
          │ Null Move      │                    │
          │ QSearch        │                    │
          └───────┬────────┘                    │
                  │                             │
                  └─────────────┬───────────────┘
                                │
                         ┌──────▼──────┐
                         │    BOARD    │
                         │            │
                         │ Bitboards  │
                         │ MoveGen    │
                         │ Zobrist    │
                         └─────────────┘


Interactive analysis/explanation:

position / move / question
          │
          ▼
   chess engine analysis
          │
          ▼
 structured eval context
          │
          ▼
     local LLM
          │
          ▼
 natural-language answer


Match/training ecosystem:

our engine ◄────UCI match runner────► external engine
    │                                  (Stockfish,
    │                                   friend's engine,
    │                                   older versions)
    │
    └── startpos / FEN / forced line / opening suite


Offline improvement system:

self-play + external-engine games
   │
   ▼
game / position database
   │
   ▼
training + tuning
   │
   ▼
candidate evaluator/network
   │
   ▼
automated testing
   │
   ├── reject ──► discard
   │
   └── accept ──► new engine version
```

---

# 86. Guiding principle

The project should evolve in this order:

```text
Correct chess
    ↓
Correct search
    ↓
Fast search
    ↓
Good evaluation
    ↓
Strong engine
    ↓
Explainable analysis
    ↓
Self-play
    ↓
Automated tuning
    ↓
Learned evaluation
    ↓
Continuous improvement
```

At every stage, the engine must remain testable and measurable.

The learning system should improve an already functional chess engine rather than compensate for an unreliable implementation.


---

# 87. External-engine interoperability requirements

The engine ecosystem must treat external engines as first-class opponents.

Minimum target:

```text
Any local UCI-compatible engine executable
```

The match runner must handle:

```text
process startup
UCI handshake
engine readiness
position synchronization
clock updates
bestmove parsing
illegal-move detection
timeouts
engine crashes
game termination
PGN generation
```

If an external engine crashes or returns an illegal move:

```text
record failure
record engine output/log
terminate or adjudicate game according to configured policy
```

External engines must never need access to this engine's internal classes.

Interoperability occurs through the protocol layer.

---

# 88. Controlled-position training requirements

The project must make it trivial to answer requests such as:

```text
Play 500 games against Stockfish from the Grünfeld.
Always train our engine as Black.
Force the first 12 plies.
After that, both engines calculate freely.
Do not use our opening book.
```

or:

```text
Take this FEN.
Play it 100 times against my friend's engine.
Swap colors every game.
```

or:

```text
Use this exact PGN line for the first 18 plies.
Then release both engines.
Our engine may use its own book after release.
```

This functionality belongs to the match/training orchestration layer, not to the core search algorithm.

---

# 89. Analysis + LLM separation of responsibilities

The system is intentionally split into three layers:

```text
1. Chess engine
   calculates

2. Analysis formatter
   structures and exposes evidence

3. Local LLM
   explains and answers questions
```

The local LLM must not decide the engine's move.

The local LLM must not modify the numeric evaluation.

The local LLM may:

```text
summarize
compare
explain
answer follow-up questions
translate engine features into chess concepts
```

The engine remains authoritative for:

```text
legality
search
scores
PV
best move
candidate ordering
mate claims
```

---

# 90. New project acceptance scenarios

The following scenarios must eventually work end-to-end.

## Scenario A — Free engine match

```text
our engine vs Stockfish
start from move 1
no book
paired colors
100 games
```

## Scenario B — Opening-specific training

```text
our engine as Black
vs Stockfish
Grünfeld Defence
forced opening prefix
release after configured ply
200 games
```

## Scenario C — Exact line training

```text
user provides PGN/UCI line
runner validates it
runner forces it
engines continue freely
```

## Scenario D — Arbitrary-position training

```text
user supplies FEN
engines start there
colors can be fixed or swapped
```

## Scenario E — Own-book play

```text
OwnBook = true
engine queries its database
selects book move
falls back to search out of book
```

## Scenario F — Think from move 1

```text
OwnBook = false
engine searches the initial position itself
```

## Scenario G — Detailed analysis

For each move:

```text
searched score
static score
material
mobility
piece activity
pawn structure
king safety
space
other enabled components
PV
best alternative
```

## Scenario H — Ask the local assistant

User selects a position and asks:

```text
"Why does the engine think Black is better?"
```

System flow:

```text
engine computes/loads analysis
→ structured context is generated
→ local LLM receives evidence
→ answer references concrete engine data
```

If more calculation is required:

```text
LLM/tooling requests additional engine search
→ analysis is updated
→ explanation is regenerated
```
