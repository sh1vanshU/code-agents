"""Sprint Velocity Predictor — predict sprint capacity from git history.

Analyzes commit frequency, complexity patterns, and historical velocity
to predict team capacity and detect overcommitment.
"""

from __future__ import annotations

import logging
import math
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.domain.velocity_predict")

# Typical sprint length in days
_DEFAULT_SPRINT_DAYS = 14
# Weeks of history to consider
_DEFAULT_HISTORY_WEEKS = 12


@dataclass
class VelocityReport:
    """Sprint velocity prediction report."""

    avg_velocity: float
    predicted_capacity: int
    committed: int
    overcommit: bool
    weekly_velocities: list[float] = field(default_factory=list)
    trend: str = ""  # "increasing", "decreasing", "stable"
    confidence: float = 0.0  # 0.0 to 1.0
    avg_complexity: float = 0.0

    def summary(self) -> str:
        """One-line summary."""
        status = "OVERCOMMITTED" if self.overcommit else "OK"
        return (
            f"Avg velocity: {self.avg_velocity:.1f} | "
            f"Predicted capacity: {self.predicted_capacity} | "
            f"Committed: {self.committed} | "
            f"Status: {status} | "
            f"Trend: {self.trend}"
        )


class VelocityPredictor:
    """Predict sprint velocity and capacity from git history."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("VelocityPredictor initialized, cwd=%s", cwd)

    def predict(self, committed_points: int = 0) -> VelocityReport:
        """Predict sprint capacity based on historical data.

        Args:
            committed_points: Points committed for the upcoming sprint.
                If > 0, checks for overcommitment.

        Returns:
            VelocityReport with prediction and analysis.
        """
        logger.info("Predicting velocity, committed=%d", committed_points)

        historical = self._get_historical()
        if not historical:
            logger.warning("No historical data available")
            return VelocityReport(
                avg_velocity=0.0,
                predicted_capacity=0,
                committed=committed_points,
                overcommit=False,
                trend="unknown",
                confidence=0.0,
            )

        # Calculate weekly velocities (proxy: commit-weighted complexity)
        weekly_velocities = [w["velocity"] for w in historical]

        # Average velocity
        avg_velocity = sum(weekly_velocities) / len(weekly_velocities) if weekly_velocities else 0.0

        # Predicted capacity: use weighted average (recent weeks count more)
        predicted = self._weighted_prediction(weekly_velocities)

        # Scale to sprint (2 weeks default)
        sprint_capacity = int(round(predicted * (_DEFAULT_SPRINT_DAYS / 7)))

        # Trend detection
        trend = self._detect_trend(weekly_velocities)

        # Confidence based on data volume and consistency
        confidence = self._calculate_confidence(weekly_velocities)

        # Average complexity
        complexities = [w.get("avg_complexity", 0.0) for w in historical]
        avg_complexity = sum(complexities) / len(complexities) if complexities else 0.0

        # Overcommit check
        overcommit = committed_points > sprint_capacity if committed_points > 0 else False

        report = VelocityReport(
            avg_velocity=round(avg_velocity, 2),
            predicted_capacity=sprint_capacity,
            committed=committed_points,
            overcommit=overcommit,
            weekly_velocities=weekly_velocities,
            trend=trend,
            confidence=round(confidence, 2),
            avg_complexity=round(avg_complexity, 2),
        )
        logger.info("Prediction: %s", report.summary())
        return report

    def _get_historical(self) -> list[dict]:
        """Get historical velocity data from git log.

        Extracts commits per week with file-change complexity estimates.

        Returns:
            List of weekly data dicts with keys: week, commits, velocity, avg_complexity.
        """
        since = (datetime.now() - timedelta(weeks=_DEFAULT_HISTORY_WEEKS)).strftime("%Y-%m-%d")

        try:
            result = subprocess.run(
                [
                    "git", "log", f"--since={since}",
                    "--format=%H|%aI|%s",
                    "--shortstat",
                ],
                capture_output=True,
                text=True,
                cwd=self.cwd,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning("git log failed: %s", result.stderr.strip())
                return []
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("git log failed: %s", exc)
            return []

        return self._parse_git_log(result.stdout)

    def _parse_git_log(self, output: str) -> list[dict]:
        """Parse git log output into weekly velocity data."""
        weekly: dict[str, list[dict]] = defaultdict(list)

        lines = output.strip().splitlines()
        current_commit: dict | None = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if "|" in line and len(line.split("|")) >= 3:
                parts = line.split("|", 2)
                sha = parts[0].strip()
                date_str = parts[1].strip()
                subject = parts[2].strip()

                try:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    week_key = dt.strftime("%Y-W%W")
                except (ValueError, IndexError):
                    week_key = "unknown"

                current_commit = {
                    "sha": sha,
                    "week": week_key,
                    "subject": subject,
                    "files_changed": 0,
                    "insertions": 0,
                    "deletions": 0,
                }
            elif current_commit and ("file" in line or "insertion" in line or "deletion" in line):
                # Parse shortstat line: "3 files changed, 45 insertions(+), 12 deletions(-)"
                files_m = re.search(r"(\d+) file", line)
                ins_m = re.search(r"(\d+) insertion", line)
                del_m = re.search(r"(\d+) deletion", line)

                current_commit["files_changed"] = int(files_m.group(1)) if files_m else 0
                current_commit["insertions"] = int(ins_m.group(1)) if ins_m else 0
                current_commit["deletions"] = int(del_m.group(1)) if del_m else 0

                weekly[current_commit["week"]].append(current_commit)
                current_commit = None

        # Aggregate per week
        result: list[dict] = []
        for week_key in sorted(weekly.keys()):
            commits = weekly[week_key]
            total_commits = len(commits)
            complexities = [self._estimate_complexity(c["files_changed"]) for c in commits]
            avg_complexity = sum(complexities) / len(complexities) if complexities else 0.0
            velocity = sum(complexities)

            result.append({
                "week": week_key,
                "commits": total_commits,
                "velocity": round(velocity, 2),
                "avg_complexity": round(avg_complexity, 2),
            })

        logger.debug("Parsed %d weeks of history", len(result))
        return result

    @staticmethod
    def _estimate_complexity(files_changed: int) -> float:
        """Estimate complexity points from number of files changed.

        Uses logarithmic scaling:
        - 1 file = 1.0 points
        - 5 files = ~2.6 points
        - 10 files = ~3.3 points
        - 20 files = ~4.0 points

        Args:
            files_changed: Number of files changed in a commit.

        Returns:
            Estimated complexity score.
        """
        if files_changed <= 0:
            return 0.5  # Even empty commits have some overhead
        return round(1.0 + math.log2(max(files_changed, 1)), 2)

    @staticmethod
    def _weighted_prediction(velocities: list[float]) -> float:
        """Calculate weighted average giving more weight to recent weeks.

        Recent weeks have linearly higher weights.

        Args:
            velocities: List of weekly velocity values (oldest first).

        Returns:
            Weighted average velocity.
        """
        if not velocities:
            return 0.0
        n = len(velocities)
        weights = [i + 1 for i in range(n)]  # 1, 2, 3, ... n
        total_weight = sum(weights)
        weighted_sum = sum(v * w for v, w in zip(velocities, weights))
        return weighted_sum / total_weight if total_weight > 0 else 0.0

    @staticmethod
    def _detect_trend(velocities: list[float]) -> str:
        """Detect velocity trend from weekly data.

        Args:
            velocities: List of weekly velocities (oldest first).

        Returns:
            'increasing', 'decreasing', or 'stable'.
        """
        if len(velocities) < 3:
            return "insufficient_data"

        # Compare average of first half vs second half
        mid = len(velocities) // 2
        first_half = sum(velocities[:mid]) / mid if mid > 0 else 0
        second_half = sum(velocities[mid:]) / (len(velocities) - mid) if (len(velocities) - mid) > 0 else 0

        if second_half > first_half * 1.15:
            return "increasing"
        elif second_half < first_half * 0.85:
            return "decreasing"
        return "stable"

    @staticmethod
    def _calculate_confidence(velocities: list[float]) -> float:
        """Calculate prediction confidence based on data volume and consistency.

        Args:
            velocities: List of weekly velocities.

        Returns:
            Confidence score between 0.0 and 1.0.
        """
        if not velocities:
            return 0.0

        n = len(velocities)
        # Volume factor: more weeks = more confidence (max at 12 weeks)
        volume_factor = min(n / 12, 1.0)

        # Consistency factor: lower std dev = higher confidence
        if n < 2:
            consistency_factor = 0.5
        else:
            mean = sum(velocities) / n
            if mean == 0:
                consistency_factor = 0.5
            else:
                variance = sum((v - mean) ** 2 for v in velocities) / n
                std_dev = math.sqrt(variance)
                cv = std_dev / mean  # coefficient of variation
                consistency_factor = max(0.0, 1.0 - cv)

        return min(volume_factor * 0.5 + consistency_factor * 0.5, 1.0)
