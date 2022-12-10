"""
Audits data changes in a target SQLite database.
"""

from .auditor import Event, track_changes

__all__ = ("Event", "track_changes")
