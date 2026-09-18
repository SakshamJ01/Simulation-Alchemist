"""Multi-Node Enterprise & Cloud Distribution (Phase 4J).

Provides deterministic cluster job generators for Slurm HPC and Kubernetes batch jobs,
along with distributed shard splitting for large-scale multi-node simulation sweeps.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SlurmJobConfig:
    job_name: str = "alchemist_sim"
    partition: str = "compute"
    nodes: int = 1
    ntasks_per_node: int = 16
    time_limit: str = "04:00:00"
    memory_per_cpu: str = "4G"
    output_log: str = "logs/%x_%j.out"
    error_log: str = "logs/%x_%j.err"
    array_range: str | None = None
    python_env: str = "uv run python"


class SlurmJobGenerator:
    """Generates production Slurm SBATCH job scripts for distributed HPC execution."""

    @staticmethod
    def generate_sbatch_script(config: SlurmJobConfig, command: str) -> str:
        lines = [
            "#!/bin/bash",
            f"#SBATCH --job-name={config.job_name}",
            f"#SBATCH --partition={config.partition}",
            f"#SBATCH --nodes={config.nodes}",
            f"#SBATCH --ntasks-per-node={config.ntasks_per_node}",
            f"#SBATCH --time={config.time_limit}",
            f"#SBATCH --mem-per-cpu={config.memory_per_cpu}",
            f"#SBATCH --output={config.output_log}",
            f"#SBATCH --error={config.error_log}",
        ]
        if config.array_range:
            lines.append(f"#SBATCH --array={config.array_range}")

        lines.extend([
            "",
            "set -euo pipefail",
            "echo \"Starting Simulation Alchemist distributed job on $(hostname)...\"",
            "date",
            "",
            f"{config.python_env} {command}",
            "",
            "echo \"Job completed successfully.\"",
            "date",
        ])
        return "\n".join(lines)


@dataclass(frozen=True)
class KubernetesJobConfig:
    job_name: str = "alchemist-sweep"
    namespace: str = "simulation"
    image: str = "simulation-alchemist:latest"
    cpu_request: str = "2"
    cpu_limit: str = "4"
    mem_request: str = "4Gi"
    mem_limit: str = "8Gi"
    parallelism: int = 4
    completions: int = 16
    restart_policy: str = "Never"


class KubernetesJobGenerator:
    """Generates cloud-native Kubernetes Batch Job manifest YAML definitions."""

    @staticmethod
    def generate_job_manifest(config: KubernetesJobConfig, command: list[str]) -> str:
        cmd_json = json.dumps(command)
        manifest = f"""apiVersion: batch/v1
kind: Job
metadata:
  name: {config.job_name}
  namespace: {config.namespace}
  labels:
    app.kubernetes.io/name: simulation-alchemist
    app.kubernetes.io/component: distributed-worker
spec:
  parallelism: {config.parallelism}
  completions: {config.completions}
  backoffLimit: 2
  template:
    metadata:
      name: {config.job_name}
    spec:
      restartPolicy: {config.restart_policy}
      containers:
      - name: worker
        image: {config.image}
        command: {cmd_json}
        resources:
          requests:
            cpu: "{config.cpu_request}"
            memory: "{config.mem_request}"
          limits:
            cpu: "{config.cpu_limit}"
            memory: "{config.mem_limit}"
"""
        return manifest


@dataclass(frozen=True)
class WorkloadShard:
    shard_id: int
    total_shards: int
    item_indices: list[int]


class DistributedBatchRunner:
    """Deterministic workload partitioning for multi-node distribution."""

    @staticmethod
    def partition_workload(total_items: int, num_shards: int) -> list[WorkloadShard]:
        if num_shards <= 0:
            raise ValueError("num_shards must be at least 1.")
        if total_items < 0:
            raise ValueError("total_items cannot be negative.")

        shards: list[list[int]] = [[] for _ in range(num_shards)]
        for i in range(total_items):
            shards[i % num_shards].append(i)

        return [
            WorkloadShard(shard_id=s_id, total_shards=num_shards, item_indices=indices)
            for s_id, indices in enumerate(shards)
        ]
