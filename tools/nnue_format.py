"""Read, write, and run ChessBot's portable quantized NNUE format."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess


INPUT_SIZE = 12 * 64
MAX_HIDDEN = 64


@dataclass
class QuantizedNetwork:
    version: str
    hidden_size: int
    input_quant: int
    output_quant: int
    hidden_bias: list[int]
    input_weights: list[int]
    output_bias: int
    output_weights: list[int]

    def validate(self) -> None:
        if not self.version or any(character.isspace() for character in self.version):
            raise ValueError("NNUE: version must be one non-empty token")
        if not 1 <= self.hidden_size <= MAX_HIDDEN:
            raise ValueError("NNUE: hidden size must be between 1 and 64")
        if not 1 <= self.input_quant <= 32768 or not 1 <= self.output_quant <= 32768:
            raise ValueError("NNUE: quantization must be between 1 and 32768")
        if len(self.hidden_bias) != self.hidden_size:
            raise ValueError("NNUE: invalid hidden bias count")
        if len(self.input_weights) != INPUT_SIZE * self.hidden_size:
            raise ValueError("NNUE: invalid input weight count")
        if len(self.output_weights) != self.hidden_size:
            raise ValueError("NNUE: invalid output weight count")
        if (any(not -32768 <= value <= 32767 for value in self.input_weights) or
                any(not -32768 <= value <= 32767 for value in self.output_weights)):
            raise ValueError("NNUE: weight outside int16 range")
        if any(not -100_000_000 <= value <= 100_000_000 for value in self.hidden_bias):
            raise ValueError("NNUE: hidden bias outside supported range")
        if not -10_000_000_000 <= self.output_bias <= 10_000_000_000:
            raise ValueError("NNUE: output bias outside supported range")

    def evaluate(self, board: chess.Board) -> int:
        accumulator = list(self.hidden_bias)
        for square, piece in board.piece_map().items():
            color = 0 if piece.color == chess.WHITE else 1
            feature = (color * 6 + piece.piece_type - 1) * 64 + square
            offset = feature * self.hidden_size
            for index in range(self.hidden_size):
                accumulator[index] += self.input_weights[offset + index]
        output = self.output_bias + sum(max(0, value) * weight for value, weight in
                                       zip(accumulator, self.output_weights, strict=True))
        white_score = max(-30_000, min(30_000,
                                      int(output / (self.input_quant * self.output_quant))))
        return white_score if board.turn == chess.WHITE else -white_score

    @property
    def memory_bytes(self) -> int:
        return len(self.hidden_bias) * 4 + len(self.input_weights) * 2 + \
               len(self.output_weights) * 2 + 8


def _take(tokens: list[str], index: int, expected: str) -> int:
    if index >= len(tokens) or tokens[index] != expected:
        raise ValueError(f"NNUE: expected {expected}")
    return index + 1


def read_network(path: Path) -> QuantizedNetwork:
    tokens = path.read_text(encoding="utf-8").split()
    index = _take(tokens, 0, "CHESSBOT_NNUE")
    if tokens[index] != "1":
        raise ValueError("NNUE: unsupported format version")
    index += 1
    index = _take(tokens, index, "version")
    version = tokens[index]
    index += 1
    index = _take(tokens, index, "architecture")
    architecture = tokens[index]
    index += 1
    index = _take(tokens, index, "hidden_size")
    hidden = int(tokens[index])
    index += 1
    if not 1 <= hidden <= MAX_HIDDEN or architecture != f"sparse_768x{hidden}_relu_1":
        raise ValueError("NNUE: invalid architecture")
    index = _take(tokens, index, "input_quant")
    input_quant = int(tokens[index])
    index += 1
    index = _take(tokens, index, "output_quant")
    output_quant = int(tokens[index])
    index += 1
    index = _take(tokens, index, "hidden_bias")
    hidden_bias = [int(value) for value in tokens[index:index + hidden]]
    index += hidden
    index = _take(tokens, index, "input_weights")
    count = INPUT_SIZE * hidden
    input_weights = [int(value) for value in tokens[index:index + count]]
    index += count
    index = _take(tokens, index, "output_bias")
    output_bias = int(tokens[index])
    index += 1
    index = _take(tokens, index, "output_weights")
    output_weights = [int(value) for value in tokens[index:index + hidden]]
    index += hidden
    index = _take(tokens, index, "END")
    if index != len(tokens):
        raise ValueError("NNUE: trailing data")
    network = QuantizedNetwork(version, hidden, input_quant, output_quant, hidden_bias,
                               input_weights, output_bias, output_weights)
    network.validate()
    return network


def write_network(path: Path, network: QuantizedNetwork) -> None:
    network.validate()
    def values(name: str, sequence: list[int]) -> str:
        return name + " " + " ".join(str(value) for value in sequence)

    lines = ["CHESSBOT_NNUE 1", f"version {network.version}",
             f"architecture sparse_768x{network.hidden_size}_relu_1",
             f"hidden_size {network.hidden_size}", f"input_quant {network.input_quant}",
             f"output_quant {network.output_quant}",
             values("hidden_bias", network.hidden_bias),
             values("input_weights", network.input_weights),
             f"output_bias {network.output_bias}",
             values("output_weights", network.output_weights), "END"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
