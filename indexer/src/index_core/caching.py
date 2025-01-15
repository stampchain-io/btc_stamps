import threading
from collections import OrderedDict
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple


class LRUCache:
    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self.cache:
                # Move to end to mark as recently used
                value = self.cache.pop(key)
                self.cache[key] = value
                return value
            return None

    def set(self, key: str, value: Any):
        with self._lock:
            if key in self.cache:
                self.cache.pop(key)
            elif len(self.cache) >= self.max_size:
                # Remove least recently used item
                self.cache.popitem(last=False)
            self.cache[key] = value

    def invalidate(self, key: str):
        with self._lock:
            self.cache.pop(key, None)


class BalanceCache:
    def __init__(self, max_size: int = 1000):
        self.cache = LRUCache(max_size)

    def get_key(self, tick: str, tick_hash: str, address: str) -> str:
        return f"{tick}:{tick_hash}:{address}"

    def get(self, tick: str, tick_hash: str, address: str) -> Optional[Decimal]:
        key = self.get_key(tick, tick_hash, address)
        return self.cache.get(key)

    def set(self, tick: str, tick_hash: str, address: str, balance: Decimal):
        key = self.get_key(tick, tick_hash, address)
        self.cache.set(key, balance)

    def invalidate(self, tick: str, tick_hash: str, address: str):
        key = self.get_key(tick, tick_hash, address)
        self.cache.invalidate(key)

    def invalidate_all(self):
        """Invalidate entire cache, used during reorgs"""
        self.cache = LRUCache(self.cache.max_size)

    def invalidate_for_tick(self, tick: str):
        """Invalidate all entries for a specific tick"""
        with self.cache._lock:
            keys_to_remove = [k for k in self.cache.cache.keys() if k.startswith(f"{tick}:")]
            for key in keys_to_remove:
                self.cache.invalidate(key)


class DeploymentCache:
    def __init__(self, max_size: int = 1000):
        self.cache = LRUCache(max_size)

    def get(self, tick: str) -> Optional[Tuple]:
        return self.cache.get(tick)

    def set(self, tick: str, deploy_data: Tuple):
        self.cache.set(tick, deploy_data)

    def invalidate(self, tick: str):
        self.cache.invalidate(tick)

    def invalidate_all(self):
        """Invalidate entire cache, used during reorgs"""
        self.cache = LRUCache(self.cache.max_size)


class BatchBalanceUpdater:
    def __init__(self, db, batch_size: int = 100):
        self.db = db
        self.batch_size = batch_size
        self.updates = []
        self._lock = threading.Lock()

    def add_update(self, tick: str, address: str, amount: Decimal, tick_hash: str, block_index: int, block_time: int):
        with self._lock:
            id_field = tick + "_" + address

            # First check existing balance, exactly as in original code
            with self.db.cursor() as cursor:
                cursor.execute("SELECT amt FROM balances WHERE id = %s", (id_field,))
                result = cursor.fetchone()
                current_balance = Decimal(result[0]) if result is not None else Decimal(0)

                # Calculate new balance
                new_balance = current_balance + amount

                # Store the update with absolute balance rather than increment
                self.updates.append((id_field, address, tick, new_balance, block_index, block_time, "SRC-20", tick_hash))

            if len(self.updates) >= self.batch_size:
                self.flush()

    def flush(self):
        if not self.updates:
            return

        with self._lock:
            updates = self.updates
            self.updates = []

        with self.db.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO balances (id, address, tick, amt, last_update, block_time, p, tick_hash) 
                VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s)
                ON DUPLICATE KEY UPDATE 
                    amt = VALUES(amt),
                    last_update = VALUES(last_update)
                """,
                updates,
            )


class TotalMintedCache:
    def __init__(self, max_size: int = 1000):
        self.cache = LRUCache(max_size)

    def get(self, tick: str) -> Optional[Decimal]:
        return self.cache.get(tick)

    def set(self, tick: str, amount: Decimal):
        self.cache.set(tick, amount)

    def invalidate(self, tick: str):
        self.cache.invalidate(tick)

    def invalidate_all(self):
        """Invalidate entire cache, used during reorgs"""
        self.cache = LRUCache(self.cache.max_size)


# Global cache instances
balance_cache = BalanceCache()
deployment_cache = DeploymentCache()
total_minted_cache = TotalMintedCache()
