from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from app.schemas import PlanRequest


class Storage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plan_cache (
                    cache_key TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_hash TEXT NOT NULL,
                    month_key TEXT NOT NULL,
                    day_key TEXT NOT NULL,
                    minute_key TEXT NOT NULL,
                    upstream_calls INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_request_month ON request_logs(month_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_request_ip_day ON request_logs(ip_hash, day_key)"
            )

    @staticmethod
    def build_cache_key(req: PlanRequest, model: str) -> str:
        payload = {
            "ingredients_text": req.ingredients_text.strip(),
            "target_calories": req.target_calories,
            "equipments": sorted(req.equipments),
            "start_timing": req.start_timing,
            "model": model,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def hash_ip(ip: str) -> str:
        return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]

    def get_cached_plan(self, cache_key: str) -> Optional[tuple[str, str]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response_json, model FROM plan_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if row:
                return row["response_json"], row["model"]
            return None

    def save_cached_plan(self, cache_key: str, response_json: str, model: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO plan_cache (cache_key, response_json, model, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cache_key, response_json, model, now),
            )

    def get_monthly_used(self) -> int:
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(upstream_calls), 0) AS total FROM request_logs WHERE month_key = ?",
                (month_key,),
            ).fetchone()
            return int(row["total"]) if row else 0

    def check_rate_limits(
        self,
        ip: str,
        monthly_limit: int,
        ip_daily_limit: int,
        ip_minute_limit: int,
    ) -> Optional[str]:
        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m")
        day_key = now.strftime("%Y-%m-%d")
        minute_key = now.strftime("%Y-%m-%dT%H:%M")
        ip_hash = self.hash_ip(ip)

        with self._connect() as conn:
            monthly_total = conn.execute(
                "SELECT COALESCE(SUM(upstream_calls), 0) AS c FROM request_logs WHERE month_key = ?",
                (month_key,),
            ).fetchone()["c"]
            if monthly_total >= monthly_limit:
                return f"今月のAI生成上限（{monthly_limit}回）に達しました。来月以降にお試しください。"

            ip_daily = conn.execute(
                "SELECT COUNT(*) AS c FROM request_logs WHERE ip_hash = ? AND day_key = ?",
                (ip_hash, day_key),
            ).fetchone()["c"]
            if ip_daily >= ip_daily_limit:
                return f"1日の利用上限（{ip_daily_limit}回/日）に達しました。明日またお試しください。"

            ip_minute = conn.execute(
                "SELECT COUNT(*) AS c FROM request_logs WHERE ip_hash = ? AND minute_key = ?",
                (ip_hash, minute_key),
            ).fetchone()["c"]
            if ip_minute >= ip_minute_limit:
                return "連続リクエスト制限中です。1分ほど待ってから再度お試しください。"

        return None

    def record_usage(self, ip: str, upstream_calls: int = 1) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO request_logs (ip_hash, month_key, day_key, minute_key, upstream_calls, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.hash_ip(ip),
                    now.strftime("%Y-%m"),
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%Y-%m-%dT%H:%M"),
                    upstream_calls,
                    now.isoformat(),
                ),
            )
