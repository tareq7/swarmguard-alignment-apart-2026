#!/usr/bin/env python3
"""Pre-sprint toy benchmark for injection propagation. NOT empirical LLM evidence."""
from __future__ import annotations
import argparse
import csv
import itertools
import random
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass(frozen=True)
class Setting:
    topology: str = "chain"
    agents: int = 20
    rounds: int = 6
    transmission: float = 0.55
    verification: float = 0.0
    seed: int = 42

    def validate(self):
        if self.topology not in ("chain", "star", "complete"):
            raise ValueError("Unsupported topology")
        if not 2 <= self.agents <= 100:
            raise ValueError("2 to 100 agents required")
        if not 0 <= self.rounds <= 50:
            raise ValueError("0 to 50 rounds required")
        if not 0 <= self.transmission <= 1 or not 0 <= self.verification <= 1:
            raise ValueError("Probabilities must be from 0 to 1")
        return self

def network(topology: str, n: int) -> list[set[int]]:
    adj = [set() for _ in range(n)]
    for a, b in itertools.combinations(range(n), 2):
        is_edge = (topology == "complete" or
                   topology == "chain" and b == a + 1 or
                   topology == "star" and a == 0)
        if is_edge:
            adj[a].add(b)
            adj[b].add(a)
    return adj

def experiment(config: Setting) -> dict:
    config.validate()
    # Agent zero is the only initial adversarial node. "Compromise" is an
    # abstract message-contagion state, not executed code or real model output.
    rng = random.Random(config.seed)
    adj = network(config.topology, config.agents)
    infected = {0}
    history = [len(infected)]
    for _ in range(config.rounds):
        newly = set()
        for source in sorted(infected):
            for dest in sorted(adj[source] - infected):
                # Independent per-link verification blocks propagation with
                # configured probability. No real signature checks occur.
                if rng.random() < config.transmission and rng.random() >= config.verification:
                    newly.add(dest)
        infected.update(newly)
        history.append(len(infected))
    return dict(asdict(config), compromised=len(infected),
                fraction=len(infected) / config.agents, history=history)

def run_matrix(seed: int, replicates: int, agents: int, rounds: int) -> list[dict]:
    if not 1 <= replicates <= 10000:
        raise ValueError("Replicates outside safe bound")
    rows = []
    for topology in ("chain", "star", "complete"):
        for verification in (0.0, 0.5, 0.9):
            for replicate in range(replicates):
                setting = Setting(topology=topology, agents=agents, rounds=rounds,
                                  verification=verification, seed=seed + replicate)
                row = experiment(setting)
                # CSV holds per-replicate values; provenance must remain clear.
                rows.append({k:v for k,v in row.items() if k != "history"})
    return rows

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--replicates", type=int, default=100)
    parser.add_argument("--agents", type=int, default=20)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--out", type=Path, default=Path("toy_results.csv"))
    args = parser.parse_args()
    rows = run_matrix(args.seed, args.replicates, args.agents, args.rounds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("Wrote", len(rows), "toy simulation rows to", args.out)

if __name__ == "__main__":
    main()
