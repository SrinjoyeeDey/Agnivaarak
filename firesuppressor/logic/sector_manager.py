"""
logic/sector_manager.py
========================
Handles radial sector ownership and exclusivity locks.
Ensures that only one nozzle is assigned to a specific angular sector
to prevent mechanical interference and multi-fire conflict.
"""

from typing import Dict, List, Optional
from loguru import logger

import time

class SectorManager:
    def __init__(self, sector_width: float = 45.0, cooldown: float = 1.5):
        self.sector_width = sector_width
        self.cooldown     = cooldown
        # sector_index -> {"fire_id": str, "last_seen": float}
        self._locks: Dict[int, dict] = {} 

    def get_sector_id(self, angle: float) -> int:
        """Requirement Phase 20: 360-degree wrap-around with cardinal centring."""
        # Shift angle by half-sector width so nozzle is in the CENTER of the sector.
        # e.g. for 90 deg sectors, Nozzle 1 (0 deg) covers 315 to 45.
        shifted_angle = (angle + self.sector_width / 2) % 360
        return int(shifted_angle // self.sector_width)

    def is_locked(self, sector_id: int, fire_id: Optional[str] = None) -> bool:
        """
        Checks if a sector is occupied. 
        If fire_id is provided, checks if it's locked by SOMEONE ELSE.
        """
        if sector_id not in self._locks:
            return False
            
        current_lock = self._locks[sector_id]
        # If fire_id is provided and matches, it's NOT locked (it's our lock)
        if fire_id and current_lock["fire_id"] == fire_id:
            return False
            
        return True

    def get_lock_by_fire_id(self, fire_id: str) -> Optional[int]:
        """Returns the sector_id currently locking this fire_id, if any."""
        for sid, lock in self._locks.items():
            if lock["fire_id"] == fire_id:
                return sid
        return None

    def lock_sector(self, sector_id: int, fire_id: str) -> bool:
        """Locks a sector for a specific fire with a timestamp."""
        self._locks[sector_id] = {
            "fire_id": fire_id,
            "last_seen": time.time()
        }
        logger.debug("🔒 Sector {} persistent lock for Fire {}", sector_id, fire_id)
        return True

    def release_stale_locks(self):
        """Removes locks that haven't been refreshed/seen for the cooldown period."""
        now = time.time()
        self._locks = {sid: lock for sid, lock in self._locks.items() 
                       if now - lock["last_seen"] < self.cooldown}

    def reset(self):
        """Compatibility: calls release_stale_locks instead of full clear."""
        self.release_stale_locks()
