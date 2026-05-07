"""Seedance Studio — parallel production pipeline targeting Seedance 2.0.

Isolated from the existing Veo flow. See plan file at
~/.claude/plans/evrithing-is-working-as-keen-parrot.md and the project memory
at ~/.claude/projects/.../memory/project_seedance_studio.md for design rationale.
"""

from .routes import register_routes

__all__ = ["register_routes"]
