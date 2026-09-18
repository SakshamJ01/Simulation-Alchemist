"""Tests for Multi-Node Distribution, Slurm and Kubernetes Job Generators (Phase 4J)."""

from __future__ import annotations

from sim_alchemist.core.distribution import (
    DistributedBatchRunner,
    KubernetesJobConfig,
    KubernetesJobGenerator,
    SlurmJobConfig,
    SlurmJobGenerator,
)


def test_slurm_job_generator() -> None:
    cfg = SlurmJobConfig(job_name="morpho_sweep", partition="gpu", ntasks_per_node=32, time_limit="02:00:00")
    script = SlurmJobGenerator.generate_sbatch_script(cfg, command="run_sweep.py --config sweep.yaml")

    assert "#SBATCH --job-name=morpho_sweep" in script
    assert "#SBATCH --partition=gpu" in script
    assert "#SBATCH --ntasks-per-node=32" in script
    assert "uv run python run_sweep.py --config sweep.yaml" in script


def test_kubernetes_job_generator() -> None:
    cfg = KubernetesJobConfig(job_name="alchemist-k8s", parallelism=8, completions=32)
    manifest = KubernetesJobGenerator.generate_job_manifest(cfg, command=["python", "run_search.py"])

    assert "kind: Job" in manifest
    assert "name: alchemist-k8s" in manifest
    assert "parallelism: 8" in manifest
    assert "completions: 32" in manifest


def test_distributed_workload_partitioning() -> None:
    shards = DistributedBatchRunner.partition_workload(total_items=10, num_shards=3)
    assert len(shards) == 3
    # Shard 0 gets 0, 3, 6, 9
    assert shards[0].item_indices == [0, 3, 6, 9]
    # Shard 1 gets 1, 4, 7
    assert shards[1].item_indices == [1, 4, 7]
    # Shard 2 gets 2, 5, 8
    assert shards[2].item_indices == [2, 5, 8]
