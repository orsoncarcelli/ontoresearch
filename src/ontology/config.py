"""Kernel configuration — thin in v1.0."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class KernelConfig(BaseSettings):
    """Configuration for the ontology kernel.

    Reads from environment variables with ONTOLOGY_ prefix.
    Example: ONTOLOGY_BACKEND=networkx
    """

    model_config = {"env_prefix": "ONTOLOGY_"}

    backend: Literal["networkx", "kuzu", "neo4j"] = "networkx"
    persist_path: Path = Path("data/ontology.json")
    default_namespace: str = "default"
    auto_discover_plugins: bool = True
