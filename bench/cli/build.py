"""Build commands for SSEBench CLI."""

import logging
import subprocess
from pathlib import Path

from pipe import build_pipe
from tasks import LocalTask
from tasks.task import Task

logger = logging.getLogger(__name__)


def discover_tasks(benchmarks_dir: Path) -> list[Task]:
    """Discover SSEBench tasks from a benchmarks directory.

    Args:
        benchmarks_dir: Path to the benchmarks directory.

    Returns:
        List of Task objects for valid tasks.
    """
    tasks: list[Task] = []
    if not benchmarks_dir.exists():
        logger.warning(f"Benchmarks directory {benchmarks_dir} does not exist")
        return tasks

    for task_dir in sorted(benchmarks_dir.iterdir()):
        if task_dir.is_dir() and not task_dir.name.startswith("."):
            # Check if it looks like a valid task (has Dockerfile or src/)
            if (task_dir / "Dockerfile").exists() or (task_dir / "src").exists():
                try:
                    task = LocalTask(task_dir.name, benchmarks_dir)
                    tasks.append(task)
                except FileNotFoundError:
                    logger.warning(f"Could not load task from {task_dir}")

    return tasks


def get_tasks(benchmarks_dir: Path, task_names: str | None = None) -> list[Task]:
    """Get tasks either by discovery or by explicit names.

    Args:
        benchmarks_dir: Path to the benchmarks directory.
        task_names: Optional comma-separated list of task names.

    Returns:
        List of Task objects.
    """
    if task_names:
        tasks: list[Task] = []
        for name in task_names.split(","):
            name = name.strip()
            try:
                task = LocalTask(name, benchmarks_dir)
                tasks.append(task)
            except FileNotFoundError:
                logger.error(f"Task {name} not found in {benchmarks_dir}")
        return tasks
    else:
        return discover_tasks(benchmarks_dir)


def build_case_image(task: Task, force: bool = False) -> bool:
    """Build a case image for a task.

    Args:
        task: The Task to build.
        force: If True, rebuild even if image exists.

    Returns:
        True if successful, False otherwise.
    """
    if not force and task.case_image_exists():
        logger.info(f"Skipping {task.name} - case image already exists (use --force to rebuild)")
        return True

    try:
        logger.info(f"Building case image for {task.name}...")
        build_pipe([task])
        logger.info(f"Successfully built {task.docker_image_name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to build case image for {task.name}: {e}")
        return False
