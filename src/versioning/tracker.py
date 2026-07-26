"""CineOS Component Version Tracker

Tracks versions for all system components: workflow, prompt, database,
worker, api, config, model. Stores version history in the
cineos_config.versions table with compatibility metadata and rollback support.
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger("cineos.versioning")

# Valid component names
COMPONENTS = frozenset([
    "workflow",
    "prompt",
    "database",
    "worker",
    "api",
    "config",
    "model",
])


class VersionTracker:
    """Tracks and manages versions for CineOS components.

    Each component can have multiple versioned entries. Versions follow
    semantic versioning (MAJOR.MINOR.PATCH). The tracker maintains a
    history of all changes, supports compatibility checks, and allows
    rollback to any previous version.

    Usage:
        tracker = VersionTracker()
        tracker.bump_version("workflow", "Added fight choreography", author="alice")
        current = tracker.get_current_version("workflow")
        history = tracker.get_version_history("workflow")
        tracker.rollback("workflow", "1.2.0")
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        dbname: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.host = host or os.getenv("POSTGRES_HOST", "localhost")
        self.port = port or int(os.getenv("POSTGRES_PORT", "5432"))
        self.dbname = dbname or os.getenv("POSTGRES_DB", "cineos")
        self.user = user or os.getenv("POSTGRES_USER", "cineos")
        self.password = password or os.getenv("POSTGRES_PASSWORD", "cineos")

    def _connect(self):
        """Create a new database connection."""
        return psycopg2.connect(
            host=self.host,
            port=self.port,
            dbname=self.dbname,
            user=self.user,
            password=self.password,
        )

    def _ensure_table(self):
        """Ensure the versions table exists."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS cineos_config.versions (
                        version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        component VARCHAR(50) NOT NULL,
                        version_number VARCHAR(20) NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        created_by VARCHAR(200),
                        reason TEXT,
                        compatibility JSONB,
                        metadata JSONB,
                        UNIQUE(component, version_number)
                    )
                """)
                conn.commit()

    def _validate_component(self, component: str):
        """Validate component name."""
        if component not in COMPONENTS:
            raise ValueError(
                f"Invalid component '{component}'. "
                f"Must be one of: {', '.join(sorted(COMPONENTS))}"
            )

    def _get_next_version(self, component: str, bump_type: str = "patch") -> str:
        """Calculate next version number for a component."""
        current = self.get_current_version(component)
        if current is None:
            return "1.0.0"

        parts = current.split(".")
        if len(parts) != 3:
            return "1.0.0"

        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

        if bump_type == "major":
            return f"{major + 1}.0.0"
        elif bump_type == "minor":
            return f"{major}.{minor + 1}.0"
        else:
            return f"{major}.{minor}.{patch + 1}"

    def get_current_version(self, component: str) -> Optional[str]:
        """Return the current (most recent) version of a component.

        Args:
            component: Component name (workflow, prompt, database, etc.)

        Returns:
            Version string like "1.2.3" or None if no version exists.
        """
        self._validate_component(component)

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT version_number
                        FROM cineos_config.versions
                        WHERE component = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (component,))
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error("Failed to get current version for %s: %s", component, e)
            raise

    def bump_version(
        self,
        component: str,
        reason: str,
        author: str = "system",
        bump_type: str = "patch",
        compatibility: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new version for a component.

        Args:
            component: Component name.
            reason: Description of why this version was created.
            author: Who created this version.
            bump_type: One of "major", "minor", "patch".
            compatibility: Dict of compatibility constraints, e.g.
                {"requires_database": ">=1.2.0", "requires_worker": ">=2.0.0"}.
            metadata: Arbitrary metadata dict.

        Returns:
            The new version number string.
        """
        self._validate_component(component)
        if bump_type not in ("major", "minor", "patch"):
            raise ValueError(f"bump_type must be major, minor, or patch, got '{bump_type}'")

        new_version = self._get_next_version(component, bump_type)

        self._ensure_table()

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO cineos_config.versions
                            (component, version_number, created_by, reason,
                             compatibility, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        component,
                        new_version,
                        author,
                        reason,
                        psycopg2.extras.Json(compatibility or {}),
                        psycopg2.extras.Json(metadata or {}),
                    ))
                    conn.commit()

            logger.info(
                "Bumped %s to %s by %s: %s",
                component, new_version, author, reason,
            )
            return new_version

        except psycopg2.IntegrityError as e:
            conn.rollback()
            logger.error(
                "Version %s already exists for %s: %s",
                new_version, component, e,
            )
            raise ValueError(
                f"Version {new_version} already exists for component '{component}'"
            )
        except Exception as e:
            logger.error("Failed to bump version for %s: %s", component, e)
            raise

    def get_version_history(
        self,
        component: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return version history for a component, newest first.

        Args:
            component: Component name.
            limit: Maximum number of versions to return.

        Returns:
            List of dicts with keys: version_id, version_number,
            created_at, created_by, reason, compatibility, metadata.
        """
        self._validate_component(component)

        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            version_id::text,
                            component,
                            version_number,
                            created_at::text,
                            created_by,
                            reason,
                            compatibility,
                            metadata
                        FROM cineos_config.versions
                        WHERE component = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (component, limit))
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error("Failed to get version history for %s: %s", component, e)
            raise

    def check_compatibility(
        self,
        component: str,
        version: str,
    ) -> Dict[str, Any]:
        """Check if a component version is compatible with current state.

        Evaluates the compatibility constraints stored in the version record
        against the current versions of other components.

        Args:
            component: Component name.
            version: Version number to check.

        Returns:
            Dict with keys:
                compatible (bool): True if all constraints satisfied.
                version (str): The version being checked.
                component (str): The component being checked.
                issues (list[str]): List of incompatibility descriptions.
                checked_at (str): ISO timestamp of check.
        """
        self._validate_component(component)

        result = {
            "compatible": True,
            "version": version,
            "component": component,
            "issues": [],
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT compatibility
                        FROM cineos_config.versions
                        WHERE component = %s AND version_number = %s
                    """, (component, version))
                    row = cur.fetchone()

                    if not row or not row["compatibility"]:
                        return result

                    compat = row["compatibility"]

                    # Check each compatibility constraint
                    for req_key, req_value in compat.items():
                        # Keys like "requires_database", "requires_worker"
                        req_component = req_key.replace("requires_", "")

                        if req_component not in COMPONENTS:
                            continue

                        current_ver = self.get_current_version(req_component)
                        if current_ver is None:
                            result["issues"].append(
                                f"Required component '{req_component}' has no versions"
                            )
                            result["compatible"] = False
                            continue

                        # Parse version constraint (>=, <=, =, etc.)
                        if not self._check_version_constraint(
                            current_ver, req_value
                        ):
                            result["issues"].append(
                                f"Component '{req_component}' version {current_ver} "
                                f"does not satisfy constraint '{req_value}'"
                            )
                            result["compatible"] = False

                    return result

        except Exception as e:
            logger.error(
                "Failed to check compatibility for %s %s: %s",
                component, version, e,
            )
            raise

    def _check_version_constraint(
        self,
        current: str,
        constraint: str,
    ) -> bool:
        """Check if a version satisfies a constraint string.

        Supports: >=X.Y.Z, <=X.Y.Z, >X.Y.Z, <X.Y.Z, =X.Y.Z, X.Y.Z (exact).
        """
        constraint = constraint.strip()

        if constraint.startswith(">="):
            return self._parse_version(current) >= self._parse_version(constraint[2:])
        elif constraint.startswith("<="):
            return self._parse_version(current) <= self._parse_version(constraint[2:])
        elif constraint.startswith(">"):
            return self._parse_version(current) > self._parse_version(constraint[1:])
        elif constraint.startswith("<"):
            return self._parse_version(current) < self._parse_version(constraint[1:])
        elif constraint.startswith("="):
            return self._parse_version(current) == self._parse_version(constraint[1:])
        else:
            return self._parse_version(current) == self._parse_version(constraint)

    @staticmethod
    def _parse_version(version: str) -> tuple:
        """Parse version string into comparable tuple."""
        try:
            parts = version.strip().split(".")
            return tuple(int(p) for p in parts)
        except (ValueError, AttributeError):
            return (0, 0, 0)

    def rollback(
        self,
        component: str,
        target_version: str,
        author: str = "system",
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Rollback a component to a previous version.

        Creates a new version entry that marks the rollback. The target
        version's metadata is carried forward. This does NOT modify
        existing version records — it creates a new entry that references
        the rollback target.

        Args:
            component: Component name.
            target_version: The version number to roll back to.
            author: Who initiated the rollback.
            reason: Optional reason for the rollback.

        Returns:
            Dict with keys:
                rolled_back (bool): True if successful.
                from_version (str): Previous version before rollback.
                to_version (str): The target version rolled back to.
                new_version (str): The newly created rollback version entry.
                created_at (str): ISO timestamp.
        """
        self._validate_component(component)

        current_version = self.get_current_version(component)
        if current_version is None:
            raise ValueError(
                f"Cannot rollback component '{component}': no versions exist"
            )

        if current_version == target_version:
            raise ValueError(
                f"Cannot rollback: already at version {target_version}"
            )

        # Verify target version exists
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT metadata, compatibility
                        FROM cineos_config.versions
                        WHERE component = %s AND version_number = %s
                    """, (component, target_version))
                    target_row = cur.fetchone()

                    if not target_row:
                        raise ValueError(
                            f"Target version {target_version} does not exist "
                            f"for component '{component}'"
                        )

                    # Create new version entry for the rollback
                    rollback_reason = reason or f"Rollback from {current_version} to {target_version}"
                    new_version = self._get_next_version(component, "patch")

                    cur.execute("""
                        INSERT INTO cineos_config.versions
                            (component, version_number, created_by, reason,
                             compatibility, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        component,
                        new_version,
                        author,
                        rollback_reason,
                        target_row["compatibility"],
                        psycopg2.extras.Json({
                            "rollback": True,
                            "rollback_from": current_version,
                            "rollback_to": target_version,
                            "original_metadata": target_row["metadata"],
                        }),
                    ))
                    conn.commit()

            logger.info(
                "Rolled back %s from %s to %s (new entry: %s)",
                component, current_version, target_version, new_version,
            )

            return {
                "rolled_back": True,
                "from_version": current_version,
                "to_version": target_version,
                "new_version": new_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "Failed to rollback %s to %s: %s",
                component, target_version, e,
            )
            raise

    def get_all_versions(self) -> Dict[str, Dict[str, Any]]:
        """Return the current version of every component.

        Returns:
            Dict mapping component names to their current version info.
        """
        result = {}
        for component in sorted(COMPONENTS):
            try:
                current = self.get_current_version(component)
                history = self.get_version_history(component, limit=1)
                if history:
                    result[component] = {
                        "current_version": current,
                        "last_change": history[0].get("reason", ""),
                        "last_author": history[0].get("created_by", ""),
                        "last_updated": history[0].get("created_at", ""),
                    }
                else:
                    result[component] = {
                        "current_version": None,
                        "last_change": "",
                        "last_author": "",
                        "last_updated": "",
                    }
            except Exception as e:
                logger.warning("Failed to get version for %s: %s", component, e)
                result[component] = {
                    "current_version": "error",
                    "last_change": str(e),
                    "last_author": "",
                    "last_updated": "",
                }
        return result
