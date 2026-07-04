"""Static configuration: service profiles."""
from .profiles import (
    PROFILES,
    ServiceProfile,
    get_profile,
    profile_for_domain,
)

__all__ = ["PROFILES", "ServiceProfile", "get_profile", "profile_for_domain"]
