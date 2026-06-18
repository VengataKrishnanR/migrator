"""Migration chunking strategy for incremental, parallelizable execution.

Breaks large Angular projects into manageable chunks based on dependency
graph, complexity, and token estimates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    AnalysisReport,
    Component,
    MigrationChunk,
    MigrationPlan,
    Service,
)


@dataclass
class ChunkingStrategy:
    """Configuration for migration chunking."""

    max_chunk_tokens: int = 8000       # Target tokens per chunk
    max_files_per_chunk: int = 5       # Max files in a single chunk
    prioritize_by: str = "dependency"  # dependency | complexity | risk
    enable_parallelization: bool = True
    group_related_files: bool = True   # Group component + template + styles


class MigrationChunker:
    """Builds migration chunks from analysis report."""

    def __init__(self, strategy: ChunkingStrategy | None = None):
        """Initialize chunker with strategy.

        Args:
            strategy: Chunking configuration (defaults to balanced strategy)
        """
        self.strategy = strategy or ChunkingStrategy()

    def build_plan(self, analysis: AnalysisReport) -> MigrationPlan:
        """Build migration plan with dependency-ordered chunks.

        Args:
            analysis: Output from analyzer_agent

        Returns:
            Executable migration plan with chunks and ordering
        """
        chunks: list[MigrationChunk] = []

        # Build component chunks
        for idx, component in enumerate(analysis.components):
            chunk_id = f"component_{component.name}_{idx}"
            source_files = [component.path]

            # Group related files if strategy permits
            if self.strategy.group_related_files:
                # Add template file (if external)
                if component.template_type == "external":
                    template_path = component.path.replace(".ts", ".html")
                    source_files.append(template_path)
                # Add styles
                style_path = component.path.replace(".ts", ".css")
                source_files.append(style_path)

            chunks.append(
                MigrationChunk(
                    chunk_id=chunk_id,
                    type="component",
                    source_files=source_files,
                    dependencies=component.dependencies,
                    priority=self._calculate_priority(component),
                    estimated_tokens=self._estimate_tokens(component),
                )
            )

        # Build service chunks
        for idx, service in enumerate(analysis.services):
            chunk_id = f"service_{service.name}_{idx}"
            chunks.append(
                MigrationChunk(
                    chunk_id=chunk_id,
                    type="service",
                    source_files=[service.path],
                    dependencies=service.dependencies,
                    priority=self._calculate_service_priority(service),
                    estimated_tokens=self._estimate_service_tokens(service),
                )
            )

        # Translate Angular class-name dependencies to chunk IDs so that
        # topological sort can compare them correctly.
        # e.g. dependency "UserService" → chunk_id "service_UserService_0"
        name_to_chunk_id: dict[str, str] = {}
        for chunk in chunks:
            parts = chunk.chunk_id.split("_")
            # chunk_id format: "<type>_<Name>_<idx>"
            # Extract the name part (middle segment, may contain no underscores for CamelCase names)
            if len(parts) >= 3:
                entity_name = "_".join(parts[1:-1])
                name_to_chunk_id[entity_name] = chunk.chunk_id

        for chunk in chunks:
            chunk.dependencies = [
                name_to_chunk_id.get(dep, dep) for dep in chunk.dependencies
            ]

        # Build execution order (topological sort by dependencies)
        execution_order = self._topological_sort(chunks)

        # Build parallel groups if enabled
        parallel_groups = []
        if self.strategy.enable_parallelization:
            parallel_groups = self._build_parallel_groups(chunks, execution_order)

        total_tokens = sum(c.estimated_tokens for c in chunks)

        return MigrationPlan(
            chunks=chunks,
            execution_order=execution_order,
            parallel_groups=parallel_groups,
            total_estimated_tokens=total_tokens,
            recommended_batch_size=self.strategy.max_files_per_chunk,
        )

    def _calculate_priority(self, component: Component) -> int:
        """Calculate component migration priority (higher = more important)."""
        priority = 1

        # Boost if used by many others (check dependencies)
        priority += len([d for d in component.dependencies if d])

        # Boost if has complex features
        if component.has_forms:
            priority += 2
        if component.has_router:
            priority += 2
        if len(component.lifecycle_hooks) > 3:
            priority += 1

        return priority

    def _calculate_service_priority(self, service: Service) -> int:
        """Calculate service migration priority."""
        priority = 1

        # Services are typically high priority (used by components)
        priority += len(service.dependencies) + len(service.http_calls)

        return priority

    def _estimate_tokens(self, component: Component) -> int:
        """Rough token estimate for component migration."""
        base = 500  # Base overhead

        # Add for complexity
        base += len(component.inputs) * 50
        base += len(component.outputs) * 50
        base += len(component.lifecycle_hooks) * 100
        base += len(component.dependencies) * 50

        if component.has_forms:
            base += 500
        if component.has_router:
            base += 300

        return min(base, self.strategy.max_chunk_tokens)

    def _estimate_service_tokens(self, service: Service) -> int:
        """Rough token estimate for service migration."""
        base = 300
        base += len(service.dependencies) * 50
        base += len(service.http_calls) * 100
        return min(base, self.strategy.max_chunk_tokens)

    def _topological_sort(self, chunks: list[MigrationChunk]) -> list[str]:
        """Sort chunks by dependency order (leaves first).

        Args:
            chunks: List of migration chunks

        Returns:
            Ordered list of chunk IDs
        """
        # Build dependency map
        dep_map: dict[str, set[str]] = {}
        for chunk in chunks:
            dep_map[chunk.chunk_id] = set(chunk.dependencies)

        # Kahn's algorithm for topological sort
        in_degree = {chunk.chunk_id: 0 for chunk in chunks}
        for chunk in chunks:
            for dep in chunk.dependencies:
                # Only count dependencies that exist in our chunk set
                if any(c.chunk_id == dep for c in chunks):
                    in_degree[chunk.chunk_id] += 1

        # Start with chunks that have no dependencies
        queue = [cid for cid, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # Sort by priority within same level
            queue.sort(
                key=lambda cid: next(
                    (c.priority for c in chunks if c.chunk_id == cid), 0
                ),
                reverse=True,
            )

            current = queue.pop(0)
            result.append(current)

            # Reduce in-degree for dependents
            for chunk in chunks:
                if current in chunk.dependencies:
                    in_degree[chunk.chunk_id] -= 1
                    if in_degree[chunk.chunk_id] == 0:
                        queue.append(chunk.chunk_id)

        # If result doesn't contain all chunks, there's a cycle - add remaining
        if len(result) < len(chunks):
            remaining = [c.chunk_id for c in chunks if c.chunk_id not in result]
            result.extend(remaining)

        return result

    def _build_parallel_groups(
        self, chunks: list[MigrationChunk], execution_order: list[str]
    ) -> list[list[str]]:
        """Group independent chunks that can execute in parallel.

        Args:
            chunks: All migration chunks
            execution_order: Dependency-ordered chunk IDs

        Returns:
            List of parallel execution groups
        """
        groups: list[list[str]] = []
        processed = set()

        chunk_map = {c.chunk_id: c for c in chunks}

        for chunk_id in execution_order:
            if chunk_id in processed:
                continue

            chunk = chunk_map[chunk_id]

            # Find other chunks with no shared dependencies
            parallel_group = [chunk_id]

            for other_id in execution_order:
                if other_id == chunk_id or other_id in processed:
                    continue

                other = chunk_map[other_id]

                # Check if they share dependencies
                shared_deps = set(chunk.dependencies) & set(other.dependencies)
                if not shared_deps:
                    parallel_group.append(other_id)

            groups.append(parallel_group)
            processed.update(parallel_group)

        return groups
