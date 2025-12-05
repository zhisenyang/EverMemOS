"""Memory Extraction Core Logic

Use V3 API for memory extraction.
"""

from typing import Dict, Any, List
from pathlib import Path

from agentic_layer.memory_manager import MemoryManager
from api_specs.dtos.memory_command import MemorizeRequest
from api_specs.memory_types import RawDataType
from memory_layer.memcell_extractor.base_memcell_extractor import RawData
from common_utils.datetime_utils import from_iso_format

from demo.config import ExtractModeConfig, MongoDBConfig
from demo.utils import ensure_mongo_beanie_ready


class MemoryExtractor:
    """Memory Extractor - Using V3 API"""

    def __init__(self, config: ExtractModeConfig, mongo_config: MongoDBConfig):
        """Initialize Extractor

        Args:
            config: Extraction config
            mongo_config: MongoDB config
        """
        self.config = config
        self.mongo_config = mongo_config
        self.manager: MemoryManager | None = None

    async def initialize(self) -> None:
        """Initialize MongoDB and MemoryManager"""
        await ensure_mongo_beanie_ready(self.mongo_config)
        self.manager = MemoryManager()
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def normalize_message(entry: Dict[str, Any]) -> Dict[str, Any] | None:
        """Normalize message format

        Args:
            entry: Original message dictionary

        Returns:
            Normalized message dictionary, or None if required fields are missing
        """
        # Extract timestamp
        timestamp = (
            entry.get("create_time")
            or entry.get("createTime")
            or entry.get("timestamp")
            or entry.get("created_at")
        )
        if not timestamp:
            return None

        if isinstance(timestamp, str):
            try:
                timestamp_dt = from_iso_format(timestamp)
            except Exception:
                return None
        else:
            return None

        # Extract speaker name
        speaker_name = entry.get("sender_name") or entry.get("sender")
        if not speaker_name:
            origin = entry.get("origin")
            if isinstance(origin, dict):
                speaker_name = origin.get("fullName") or origin.get("full_name")
        if not speaker_name:
            return None

        # Extract speaker ID
        raw_speaker_id = None
        origin = entry.get("origin")
        if isinstance(origin, dict):
            raw_speaker_id = origin.get("createBy") or origin.get("create_by")
        if not raw_speaker_id:
            raw_speaker_id = entry.get("sender_id") or entry.get("sender")

        return {
            "speaker_id": str(raw_speaker_id or speaker_name),
            "speaker_name": str(speaker_name),
            "content": str(entry.get("content", "")),
            "timestamp": timestamp_dt,
        }

    async def extract_from_events(self, events: List[Dict[str, Any]]) -> int:
        """Extract memories from event list

        Args:
            events: Conversation event list

        Returns:
            Number of extracted MemCells
        """
        if not self.manager:
            raise RuntimeError("Please call initialize() first")

        print("=" * 80)
        print("Extracting memories using V3 API")
        print("=" * 80)
        print(f"\n✓ Scenario Type: {self.config.scenario_type.value}")
        print(f"✓ Language: {self.config.prompt_language}")
        print(f"✓ Group ID: {self.config.group_id}")
        print(f"✓ Foresight Extraction: {self.config.enable_foresight_extraction}")
        print(f"\nProcessing {len(events)} messages...\n")

        history: List[RawData] = []
        saved_count = 0

        for idx, entry in enumerate(events):
            # Normalize message
            message_payload = self.normalize_message(entry)
            if not message_payload:
                continue

            # Extract message ID
            message_id = (
                entry.get("message_id")
                or entry.get("id")
                or entry.get("uuid")
                or entry.get("event_id")
                or f"msg_{idx}"
            )

            # Create RawData
            raw_item = RawData(
                content=message_payload,
                data_id=str(message_id),
                data_type=RawDataType.CONVERSATION,
            )

            # Initialize history
            if not history:
                history.append(raw_item)
                continue

            # Build request
            request = MemorizeRequest(
                history_raw_data_list=list(history),
                new_raw_data_list=[raw_item],
                raw_data_type=RawDataType.CONVERSATION,
                user_id_list=["default"],
                group_id=self.config.group_id,
                group_name=self.config.group_name,
                enable_foresight_extraction=self.config.enable_foresight_extraction or False,
                enable_event_log_extraction=True,
            )

            # Call V3 API
            try:
                result = await self.manager.memorize(request)

                if result:
                    saved_count += 1
                    print(
                        f"  [{saved_count:3d}] ✅ Extraction successful, returned {len(result)} Memories"
                    )
                    history = [raw_item]
                else:
                    history.append(raw_item)
                    if len(history) > self.config.history_window_size:
                        history = history[-self.config.history_window_size :]

            except Exception as e:
                print(f"\n⚠️ Extraction failed: {e}")
                history.append(raw_item)
                if len(history) > self.config.history_window_size:
                    history = history[-self.config.history_window_size :]
                continue

        print(f"\n✅ Processing complete, extracted {saved_count} MemCells")
        return saved_count
