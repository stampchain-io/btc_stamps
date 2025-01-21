"""Type definitions for the indexer."""

from typing import Optional, Tuple

# Deploy result type: (lim, max, dec)
DeployResult = Tuple[Optional[int], Optional[int], Optional[int]]
NO_DEPLOY: DeployResult = (None, None, None)
