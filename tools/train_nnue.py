"""Train and export a small sparse NNUE-style evaluator with PyTorch."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chess
import numpy as np
import torch
from torch import nn

from nnue_format import INPUT_SIZE, QuantizedNetwork, write_network


WDL_SLOPE = math.log(10) / 400


class SparseNet(nn.Module):
    def __init__(self, hidden: int):
        super().__init__()
        self.hidden = nn.Linear(INPUT_SIZE, hidden)
        self.output = nn.Linear(hidden, 1)

    def forward(self, positions: torch.Tensor) -> torch.Tensor:
        return self.output(torch.relu(self.hidden(positions))).squeeze(1)


def load_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".parquet":
        try:
            import pandas as pd
        except ImportError as error:
            raise RuntimeError("Parquet input requires pip install -e '.[training]'") from error
        return pd.read_parquet(path).to_dict("records")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def encode(fen: str) -> np.ndarray:
    result = np.zeros(INPUT_SIZE, dtype=np.float32)
    for square, piece in chess.Board(fen).piece_map().items():
        color = 0 if piece.color == chess.WHITE else 1
        result[(color * 6 + piece.piece_type - 1) * 64 + square] = 1
    return result


def teacher_score(row: dict[str, Any]) -> tuple[float, bool]:
    raw = row.get("search_score_cp")
    if raw not in (None, "", "None"):
        score = float(raw)
        perspective = row.get("search_score_perspective")
        if perspective == "black":
            score = -score
        return float(np.clip(score, -2000, 2000)), True
    score = float(row["static_total"])
    if row["side_to_move"] == "black":
        score = -score
    return float(np.clip(score, -2000, 2000)), False


def tensors(rows: list[dict[str, Any]]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor,
                                                 torch.Tensor]:
    positions = torch.from_numpy(np.stack([encode(str(row["fen"])) for row in rows]))
    outcomes = torch.tensor([float(row["result_white"]) for row in rows], dtype=torch.float32)
    teachers, searched = zip(*(teacher_score(row) for row in rows), strict=True)
    return positions, outcomes, torch.tensor(teachers), torch.tensor(searched, dtype=torch.bool)


def loss_values(prediction: torch.Tensor, outcomes: torch.Tensor, teachers: torch.Tensor,
                searched: torch.Tensor, target: str, teacher_weight: float) -> tuple[torch.Tensor,
                                                                                     dict[str, float]]:
    outcome_loss = nn.functional.binary_cross_entropy_with_logits(prediction * WDL_SLOPE,
                                                                   outcomes)
    if target == "search" and not searched.any():
        raise ValueError("search target requires search_score_cp labels")
    teacher_mask = searched if target == "search" else torch.ones_like(searched)
    teacher_loss = nn.functional.smooth_l1_loss(prediction[teacher_mask] / 400,
                                                teachers[teacher_mask] / 400)
    if target == "result":
        total = outcome_loss
    elif target == "search":
        total = teacher_loss
    else:
        total = outcome_loss + teacher_weight * teacher_loss
    return total, {"outcome_loss": float(outcome_loss.detach()),
                   "teacher_loss": float(teacher_loss.detach()), "loss": float(total.detach())}


def metrics(model: nn.Module, data: tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor],
            target: str, teacher_weight: float) -> dict[str, float]:
    model.eval()
    with torch.no_grad():
        prediction = model(data[0])
        _, losses = loss_values(prediction, data[1], data[2], data[3], target, teacher_weight)
        probability = torch.sigmoid(prediction * WDL_SLOPE)
        losses.update({"brier": float(torch.mean((probability - data[1]) ** 2)),
                       "teacher_mae_cp": float(torch.mean(torch.abs(prediction - data[2]))),
                       "mean_probability": float(torch.mean(probability)),
                       "mean_target": float(torch.mean(data[1]))})
        bins = torch.clamp((probability * 10).long(), 0, 9)
        ece = 0.0
        for index in range(10):
            selected = bins == index
            if selected.any():
                ece += float(selected.float().mean() *
                             torch.abs(probability[selected].mean() - data[1][selected].mean()))
        losses["wdl_ece"] = ece
        return losses


def quantized_metrics(network: QuantizedNetwork, rows: list[dict[str, Any]], target: str,
                      teacher_weight: float) -> dict[str, float]:
    predictions = []
    outcomes = []
    teachers = []
    searched = []
    for row in rows:
        board = chess.Board(str(row["fen"]))
        score = network.evaluate(board)
        predictions.append(float(score if board.turn == chess.WHITE else -score))
        outcomes.append(float(row["result_white"]))
        teacher, available = teacher_score(row)
        teachers.append(teacher)
        searched.append(available)
    prediction = np.asarray(predictions)
    outcome = np.asarray(outcomes)
    teacher = np.asarray(teachers)
    mask = np.asarray(searched, dtype=bool)
    if target != "search":
        mask = np.ones(len(rows), dtype=bool)
    probability = 1 / (1 + np.exp(-prediction * WDL_SLOPE))
    clipped = np.clip(probability, 1e-7, 1 - 1e-7)
    outcome_loss = float(np.mean(-outcome * np.log(clipped) - (1 - outcome) *
                                 np.log(1 - clipped)))
    difference = np.abs((prediction[mask] - teacher[mask]) / 400)
    teacher_loss = float(np.mean(np.where(difference < 1, 0.5 * difference**2,
                                          difference - 0.5)))
    total = outcome_loss if target == "result" else teacher_loss if target == "search" else \
        outcome_loss + teacher_weight * teacher_loss
    bins = np.clip((probability * 10).astype(int), 0, 9)
    ece = sum(float(np.mean(bins == index) *
                    abs(np.mean(probability[bins == index]) - np.mean(outcome[bins == index])))
              for index in range(10) if np.any(bins == index))
    return {"loss": total, "outcome_loss": outcome_loss, "teacher_loss": teacher_loss,
            "brier": float(np.mean((probability - outcome) ** 2)), "wdl_ece": ece,
            "teacher_mae_cp": float(np.mean(np.abs(prediction - teacher)))}


def quantize(model: SparseNet, version: str) -> tuple[QuantizedNetwork, dict[str, int]]:
    input_quant = output_quant = 256
    first_weight = torch.round(model.hidden.weight.detach() * input_quant).clamp(-32768, 32767)
    first_bias = torch.round(model.hidden.bias.detach() * input_quant).clamp(-100_000_000,
                                                                            100_000_000)
    second_weight = torch.round(model.output.weight.detach().squeeze(0) *
                                output_quant).clamp(-32768, 32767)
    second_bias = torch.round(model.output.bias.detach().squeeze(0) * input_quant *
                              output_quant).clamp(-10_000_000_000, 10_000_000_000)
    # C++ stores weights feature-major for sparse accumulator updates.
    weights = first_weight.t().contiguous().view(-1).to(torch.int16).tolist()
    network = QuantizedNetwork(version, model.hidden.out_features, input_quant, output_quant,
                               first_bias.to(torch.int32).tolist(), weights, int(second_bias),
                               second_weight.to(torch.int16).tolist())
    clipped = {"input_weights": int(torch.sum(torch.abs(model.hidden.weight.detach() *
                                                          input_quant) > 32767)),
               "output_weights": int(torch.sum(torch.abs(model.output.weight.detach() *
                                                           output_quant) > 32767))}
    return network, clipped


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_commit(root: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()
    except subprocess.SubprocessError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version")
    parser.add_argument("--hidden", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=0.002)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--target", choices=("result", "search", "mixed"), default="mixed")
    parser.add_argument("--teacher-weight", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--shard-dir", type=Path,
                        help="optionally cache encoded arrays as compressed NPZ shards")
    parser.add_argument("--shard-size", type=int, default=100_000)
    args = parser.parse_args()
    if not 1 <= args.hidden <= 64 or args.epochs < 1 or args.batch_size < 1:
        parser.error("hidden must be 1..64 and epoch/batch counts must be positive")
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    rows = load_rows(args.dataset)
    train_rows = [row for row in rows if row["split"] == "train"]
    validation_rows = [row for row in rows if row["split"] == "validation"]
    if not train_rows or not validation_rows:
        parser.error("dataset needs non-empty train and validation splits")
    train = tensors(train_rows)
    validation = tensors(validation_rows)
    if args.shard_dir:
        args.shard_dir.mkdir(parents=True, exist_ok=True)
        for split, data in (("train", train), ("validation", validation)):
            for index in range(0, len(data[0]), args.shard_size):
                np.savez_compressed(args.shard_dir / f"{split}-{index // args.shard_size:05d}.npz",
                                    positions=data[0][index:index + args.shard_size].numpy(),
                                    outcomes=data[1][index:index + args.shard_size].numpy(),
                                    teachers=data[2][index:index + args.shard_size].numpy(),
                                    searched=data[3][index:index + args.shard_size].numpy())
    model = SparseNet(args.hidden)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate,
                                  weight_decay=args.weight_decay)
    generator = torch.Generator().manual_seed(args.seed)
    history = []
    for epoch in range(args.epochs):
        model.train()
        permutation = torch.randperm(len(train[0]), generator=generator)
        epoch_loss = 0.0
        for start in range(0, len(permutation), args.batch_size):
            indices = permutation[start:start + args.batch_size]
            optimizer.zero_grad()
            prediction = model(train[0][indices])
            loss, _ = loss_values(prediction, train[1][indices], train[2][indices],
                                  train[3][indices], args.target, args.teacher_weight)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach()) * len(indices)
        history.append({"epoch": epoch + 1, "train_loss": epoch_loss / len(permutation)})
    version = args.version or datetime.now(UTC).strftime("nnue-%Y%m%dT%H%M%SZ")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    network, clipped = quantize(model, version)
    network_path = args.output_dir / "candidate.nnue"
    checkpoint_path = args.output_dir / "checkpoint.pt"
    write_network(network_path, network)
    torch.save({"version": version, "architecture": f"sparse_768x{args.hidden}_relu_1",
                "state_dict": model.state_dict()}, checkpoint_path)
    report = {"schema_version": 1, "version": version,
              "architecture": f"sparse_768x{args.hidden}_relu_1",
              "features": "12 color-piece planes x 64 squares; white-oriented output",
              "labels": {"target": args.target, "result": "white W/D/L as 1/0.5/0",
                         "teacher": "search_score_cp when present, otherwise static_total",
                         "teacher_weight": args.teacher_weight},
              "dataset": {"path": str(args.dataset), "sha256": sha256(args.dataset),
                          "rows": len(rows), "train": len(train_rows),
                          "validation": len(validation_rows)},
              "training": {"seed": args.seed, "epochs": args.epochs,
                           "batch_size": args.batch_size, "learning_rate": args.learning_rate,
                           "weight_decay": args.weight_decay, "torch": torch.__version__,
                           "device": "cpu", "deterministic": True, "history": history},
              "metrics": {"train": metrics(model, train, args.target, args.teacher_weight),
                          "validation": metrics(model, validation, args.target,
                                                args.teacher_weight),
                          "quantized_train": quantized_metrics(network, train_rows, args.target,
                                                               args.teacher_weight),
                          "quantized_validation": quantized_metrics(
                              network, validation_rows, args.target, args.teacher_weight)},
              "export": {"format": "CHESSBOT_NNUE 1", "input_quant": network.input_quant,
                         "output_quant": network.output_quant, "clipped": clipped,
                         "memory_bytes": network.memory_bytes,
                         "network": str(network_path), "network_sha256": sha256(network_path),
                         "checkpoint": str(checkpoint_path),
                         "checkpoint_sha256": sha256(checkpoint_path)},
              "engine_commit": git_commit(Path(__file__).resolve().parents[1])}
    report_path = args.output_dir / "training.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"network": str(network_path), "checkpoint": str(checkpoint_path),
                      "report": str(report_path), "validation": report["metrics"]["validation"]}))


if __name__ == "__main__":
    main()
