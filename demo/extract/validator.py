"""Result Validator

Validate whether extraction results are correctly stored in MongoDB, Milvus, and ES.
"""

from collections import Counter

from core.di import get_bean_by_type
from infra_layer.adapters.out.persistence.repository.memcell_raw_repository import (
    MemCellRawRepository,
)
from infra_layer.adapters.out.search.repository.episodic_memory_milvus_repository import (
    EpisodicMemoryMilvusRepository,
)
from infra_layer.adapters.out.search.repository.episodic_memory_es_repository import (
    EpisodicMemoryEsRepository,
)
from agentic_layer.vectorize_service import get_vectorize_service


class ResultValidator:
    """Result Validator"""

    def __init__(self, group_id: str):
        """Initialize Validator

        Args:
            group_id: Group ID
        """
        self.group_id = group_id

    async def validate(self) -> None:
        """Validate storage results"""
        print("\n" + "=" * 80)
        print("Validating Storage Results")
        print("=" * 80)

        # Validate MongoDB
        print("\n[MongoDB] Checking MemCell")
        memcell_repo = get_bean_by_type(MemCellRawRepository)
        memcells = await memcell_repo.find_by_group_id(self.group_id, limit=1000)
        print(f"  - Found {len(memcells)} MemCells")

        if memcells:
            total_foresight = sum(
                len(m.foresight_memories)
                for m in memcells
                if hasattr(m, 'foresight_memories') and m.foresight_memories
            )
            total_eventlog = sum(
                len(
                    m.event_log.get('atomic_fact', [])
                    if isinstance(m.event_log, dict)
                    else []
                )
                for m in memcells
                if hasattr(m, 'event_log') and m.event_log
            )

            print(f"  - episode: {len(memcells)}")
            print(f"  - foresight_memories: {total_foresight}")
            print(f"  - event_log atomic_facts: {total_eventlog}")

        # Validate Milvus
        print("\n[Milvus] Checking Records")
        milvus_repo = get_bean_by_type(EpisodicMemoryMilvusRepository)
        vectorize_service = get_vectorize_service()
        query_vector = await vectorize_service.get_embedding("test")

        # Note: limit cannot be too large, Milvus HNSW index requires ef >= k
        # Default ef=64, so limit set to max 64
        milvus_results = await milvus_repo.vector_search(
            query_vector=query_vector,
            user_id="default",
            limit=50,  # Reduce limit to avoid exceeding ef parameter (default 64)
        )
        print(f"  - Found {len(milvus_results)} records")

        if milvus_results:
            types = [r.get('memory_types', 'unknown') for r in milvus_results]
            print(f"  - Type distribution: {dict(Counter(types))}")

        # Validate ES
        print("\n[ES] Checking Records")
        es_repo = get_bean_by_type(EpisodicMemoryEsRepository)
        es_results = await es_repo.multi_search(query=[], user_id="default", size=1000)
        print(f"  - Found {len(es_results)} records")

        if es_results:
            types = [r.get('_source', {}).get('type', 'unknown') for r in es_results]
            print(f"  - Type distribution: {dict(Counter(types))}")

        # Result Summary
        print("\n" + "=" * 80)
        print("Validation Summary")
        print("=" * 80)
        print(f"\n✅ MongoDB: {len(memcells)} items")
        print(f"✅ Milvus: {len(milvus_results)} items")
        print(f"✅ ES: {len(es_results)} items")

        if len(memcells) > 0:
            print("\n🎉 Extraction and storage successful!")
        else:
            print("\n⚠️ No memory data found, please check logs")
