"""
ORBITIQ-X Backend — Conjunction Persistence Service

Persists conjunction screening results to PostgreSQL and fires
Redis pub/sub alerts for red events.

Pipeline position
─────────────────
  ConjunctionScreener (orbital-engine) produces a list of CDMs.
  This service receives those CDMs, classifies risk levels, persists
  them to conjunction_events, and publishes red alerts to Redis.

  conjunction_screener → ConjunctionPersistenceService → PostgreSQL
                                                       → Redis (alerts)
                                                       → orbital_events (log)

Risk level mapping
──────────────────
  red    : Pc ≥ 1e-3  (operator action required)
  yellow : Pc ≥ 1e-4  (monitoring required)
  green  : Pc ≥ 1e-5  (informational)
  white  : Pc <  1e-5 (below threshold, not persisted by default)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.conjunction_repository import ConjunctionRepository
from app.db.repositories.orbital_event_repository import OrbitalEventRepository
from app.db.session import transactional

logger = logging.getLogger(__name__)


# ── Risk classification ───────────────────────────────────────

def classify_risk(pc: float) -> str:
    if pc >= 1e-3: return "red"
    if pc >= 1e-4: return "yellow"
    if pc >= 1e-5: return "green"
    return "white"


def maneuver_required(pc: float) -> bool:
    return pc >= 1e-4


# ── Result ────────────────────────────────────────────────────

@dataclass
class ScreeningPersistResult:
    total_cdms: int = 0
    persisted: int = 0
    red_count: int = 0
    yellow_count: int = 0
    green_count: int = 0
    skipped_white: int = 0
    alerts_fired: int = 0
    errors: list[dict] = field(default_factory=list)


# ── Service ───────────────────────────────────────────────────

class ConjunctionPersistenceService:
    """
    Persists conjunction screening results and fires Redis alerts.

    Parameters
    ----------
    session : AsyncSession
        The database session for this operation.
    redis_client : optional
        Redis client for publishing alerts. If None, alert publishing
        is skipped (graceful degradation).
    """

    # Redis channel for red conjunction alerts
    ALERT_CHANNEL = "orbitiq:conjunction:alerts"

    def __init__(
        self,
        session: AsyncSession,
        redis_client=None,
    ) -> None:
        self.session    = session
        self.redis      = redis_client
        self.conj_repo  = ConjunctionRepository(session)
        self.event_repo = OrbitalEventRepository(session)

    async def persist_screening_results(
        self,
        cdms: list[dict],
        screening_epoch: datetime | None = None,
        persist_white: bool = False,
    ) -> ScreeningPersistResult:
        """
        Persist a batch of CDMs from a conjunction screening run.

        Parameters
        ----------
        cdms : list[dict]
            CDM dicts as produced by ConjunctionScreener. Each must have:
            primary_norad, secondary_norad, tca, miss_distance_km,
            collision_probability, relative_velocity_kms.
        screening_epoch : datetime | None
            When the screening ran (default: now).
        persist_white : bool
            If True, persist green+white events. Default False —
            white events (Pc < 1e-5) are not actionable.

        Returns
        -------
        ScreeningPersistResult
        """
        epoch = screening_epoch or datetime.now(timezone.utc)
        result = ScreeningPersistResult(total_cdms=len(cdms))

        # ── Classify and prepare records ──────────────────────
        to_persist: list[dict] = []
        red_events: list[dict] = []

        for cdm in cdms:
            pc         = float(cdm.get("collision_probability", 0))
            risk_level = classify_risk(pc)

            if risk_level == "white" and not persist_white:
                result.skipped_white += 1
                continue

            # Generate conjunction_id if not provided
            conj_id = cdm.get("conjunction_id") or (
                f"CDM-{epoch.strftime('%Y%m%d-%H%M%S')}"
                f"-{cdm.get('primary_norad', 0):05d}"
                f"-{cdm.get('secondary_norad', 0):05d}"
                f"-{uuid.uuid4().hex[:6].upper()}"
            )

            record = {
                "conjunction_id":              conj_id,
                "primary_norad":               int(cdm.get("primary_norad", 0)),
                "primary_name":                cdm.get("primary_name"),
                "primary_type":                cdm.get("primary_type"),
                "secondary_norad":             int(cdm.get("secondary_norad", 0)),
                "secondary_name":              cdm.get("secondary_name"),
                "secondary_type":              cdm.get("secondary_type"),
                "tca":                         cdm.get("tca") or epoch,
                "miss_distance_km":            float(cdm.get("miss_distance_km", 0)),
                "relative_velocity_kms":       float(cdm.get("relative_velocity_kms", 0)),
                "collision_probability":       pc,
                "collision_probability_method": cdm.get("method", "Foster2001"),
                "risk_level":                  risk_level,
                "primary_sigma_r_km":          cdm.get("primary_sigma_r_km"),
                "primary_sigma_t_km":          cdm.get("primary_sigma_t_km"),
                "primary_sigma_n_km":          cdm.get("primary_sigma_n_km"),
                "secondary_sigma_r_km":        cdm.get("secondary_sigma_r_km"),
                "secondary_sigma_t_km":        cdm.get("secondary_sigma_t_km"),
                "secondary_sigma_n_km":        cdm.get("secondary_sigma_n_km"),
                "combined_hbr_km":             cdm.get("combined_hbr_km"),
                "maneuver_required":           maneuver_required(pc),
                "maneuver_window_close":       cdm.get("maneuver_window_close"),
                "recommended_dv_kms":          cdm.get("recommended_dv_kms"),
                "resolved":                    False,
                "screening_org":               "ORBITIQ-X",
                "data_source":                 cdm.get("data_source", "computed"),
                "cdm_issued_at":               epoch,
            }
            to_persist.append(record)

            if risk_level == "red":
                result.red_count += 1
                red_events.append(record)
            elif risk_level == "yellow":
                result.yellow_count += 1
            else:
                result.green_count += 1

        # ── Bulk insert CDMs ──────────────────────────────────
        if to_persist:
            async with transactional(self.session):
                result.persisted = await self.conj_repo.bulk_insert(to_persist)

        # ── Log red/yellow events to orbital_events ──────────
        event_records = []
        for r in to_persist:
            if r["risk_level"] in ("red", "yellow"):
                event_records.append({
                    "norad_id":    r["primary_norad"],
                    "event_type":  "conjunction_alert",
                    "event_time":  r["tca"],
                    "severity":    "critical" if r["risk_level"] == "red" else "high",
                    "alert_sent":  False,
                    "title":       f"{r['risk_level'].upper()} conjunction: {r['conjunction_id']}",
                    "description": (
                        f"Pc={r['collision_probability']:.2e} "
                        f"miss={r['miss_distance_km']:.3f}km "
                        f"TCA={r['tca']}"
                    ),
                    "source_agent":  "conjunction_analysis",
                    "data_source":   "computed",
                    "extra":         {"conjunction_id": r["conjunction_id"]},
                })

        if event_records:
            async with transactional(self.session):
                await self.event_repo.bulk_log(event_records)

        # ── Publish Redis alerts for RED + YELLOW events ────────
        # RED  (Pc ≥ 1e-3): mandatory operator action
        # YELLOW (Pc ≥ 1e-4): elevated monitoring required
        # GREEN: informational only — not published to alert channel
        alert_events = [r for r in to_persist if r["risk_level"] in ("red", "yellow")]

        if alert_events and self.redis:
            from datetime import timezone as _tz
            _now = datetime.now(timezone.utc)

            for r in alert_events:
                # Compute hours remaining to TCA for dashboard urgency display
                tca = r["tca"]
                if isinstance(tca, str):
                    try:
                        from datetime import datetime as _dt
                        tca_dt = _dt.fromisoformat(tca.replace("Z", "+00:00"))
                        hours_remaining = round(
                            max(0.0, (tca_dt - _now).total_seconds() / 3600), 2
                        )
                    except Exception:
                        hours_remaining = None
                elif hasattr(tca, "tzinfo"):
                    hours_remaining = round(
                        max(0.0, (tca - _now).total_seconds() / 3600), 2
                    )
                else:
                    hours_remaining = None

                alert_payload = json.dumps({
                    # Schema matches ConjunctionItem in frontend lib/api.ts
                    "event_id":          r["conjunction_id"],
                    "conjunction_id":    r["conjunction_id"],
                    "risk_level":        r["risk_level"],
                    "probability_of_collision": r["collision_probability"],
                    "Pc":                r["collision_probability"],
                    "primary_norad":     r["primary_norad"],
                    "primary_name":      r.get("primary_name"),
                    "secondary_norad":   r["secondary_norad"],
                    "secondary_name":    r.get("secondary_name"),
                    "miss_distance_km":  r["miss_distance_km"],
                    "tca":               str(r["tca"]),
                    "hours_remaining":   hours_remaining,
                    "maneuver_required": r["maneuver_required"],
                })
                try:
                    await self.redis.publish(self.ALERT_CHANNEL, alert_payload)
                    result.alerts_fired += 1
                    log_fn = logger.warning if r["risk_level"] == "red" else logger.info
                    log_fn(
                        "%s_CONJUNCTION_ALERT conj_id=%s Pc=%.2e miss=%.3f km hours=%.1f",
                        r["risk_level"].upper(),
                        r["conjunction_id"],
                        r["collision_probability"],
                        r["miss_distance_km"],
                        hours_remaining or 0.0,
                    )
                except Exception as exc:
                    logger.error("redis_alert_failed conj_id=%s error=%s",
                                 r["conjunction_id"], exc)

        logger.info(
            "screening_persist_complete total=%d persisted=%d "
            "red=%d yellow=%d green=%d white_skipped=%d alerts=%d",
            result.total_cdms, result.persisted,
            result.red_count, result.yellow_count,
            result.green_count, result.skipped_white,
            result.alerts_fired,
        )
        return result

    async def get_active_red_events(self) -> Sequence:
        """Return all unresolved red conjunction events."""
        return await self.conj_repo.get_unresolved_red_yellow(limit=100)
