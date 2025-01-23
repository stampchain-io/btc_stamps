"""Type definitions for the indexer."""

from typing import Any, List, Optional, Tuple

# Deploy result type: (lim, max, dec)
DeployResult = Tuple[Optional[int], Optional[int], Optional[int]]
NO_DEPLOY: DeployResult = (None, None, None)

# SRC-101 deploy result type
SRC101DeployResult = Tuple[
    int,  # lim
    Optional[Any],  # pri
    int,  # mintstart
    int,  # mintend
    Optional[List[str]],  # rec
    Optional[Any],  # wla
    Optional[Any],  # imglp
    Optional[Any],  # imgf
    int,  # idua
]
