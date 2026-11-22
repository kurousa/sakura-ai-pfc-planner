from __future__ import annotations

import json
import re
from openai import OpenAI, APITimeoutError, RateLimitError, APIError
from pydantic import ValidationError

from app.config import Settings
from app.prompts import SYSTEM_PROMPT, build_correction_prompt, build_user_prompt
from app.schemas import (
    MealPlanOutput,
    PlanRequest,
    normalize_daily_totals,
    validate_plan_constraints,
)


class AIUpstreamError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def extract_json_text(raw: str) -> str:
    """コードフェンスや前後の余計な文字が混ざった場合にJSON本体を抽出する。"""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


class SakuraAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.sakura_ai_api_key:
            raise AIUpstreamError(
                "SAKURA_AI_API_KEY が未設定です。.env を確認してください。",
                status_code=500,
            )
        self.client = OpenAI(
            base_url=settings.sakura_ai_base_url,
            api_key=settings.sakura_ai_api_key,
            timeout=settings.sakura_ai_timeout_sec,
        )

    def _call_chat(self, messages: list[dict[str, str]]) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.settings.sakura_ai_model,
                messages=messages,
                temperature=0.3,
            )
            content = resp.choices[0].message.content or ""
            if not content.strip():
                raise AIUpstreamError("さくらのAI Engineから空の応答が返されました。", status_code=502)
            return content
        except RateLimitError as exc:
            raise AIUpstreamError(
                "さくらのAI Engineのレート制限（429）に達しました。しばらく待ってから再試行してください。",
                status_code=429,
            ) from exc
        except APITimeoutError as exc:
            raise AIUpstreamError(
                "さくらのAI Engineからの応答がタイムアウトしました。再度お試しください。",
                status_code=504,
            ) from exc
        except APIError as exc:
            raise AIUpstreamError(
                f"さくらのAI Engine呼び出し中にエラーが発生しました: {exc}",
                status_code=502,
            ) from exc

    def generate_plan(self, req: PlanRequest) -> tuple[MealPlanOutput, list[str], bool, int]:
        """献立プランを生成・検証し、(MealPlanOutput, warnings, retried, upstream_calls) を返す。"""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(req)},
        ]

        upstream_calls = 0
        retried = False
        last_errors: list[str] = []
        last_valid_plan: MealPlanOutput | None = None
        last_warnings: list[str] = []

        for attempt in range(2):
            raw_text = self._call_chat(messages)
            upstream_calls += 1
            json_text = extract_json_text(raw_text)

            try:
                data = json.loads(json_text)
                plan = normalize_daily_totals(MealPlanOutput.model_validate(data))
                hard_violations, soft_warnings = validate_plan_constraints(plan, req)
                last_valid_plan = plan
                last_warnings = hard_violations + soft_warnings
                if not hard_violations:
                    return plan, soft_warnings, retried, upstream_calls
                last_errors = hard_violations
            except (json.JSONDecodeError, ValidationError) as exc:
                last_errors = [f"JSON/スキーマ検証エラー: {exc}"]

            if attempt == 0:
                retried = True
                messages.append({"role": "assistant", "content": raw_text})
                messages.append({"role": "user", "content": build_correction_prompt(last_errors)})

        # 構造上有効なプランが1度でも得られていれば、全破棄せず警告付きで返却する（Graceful Degradation）
        if last_valid_plan is not None:
            return last_valid_plan, last_warnings, retried, upstream_calls

        raise AIUpstreamError(
            "献立JSONの生成に失敗しました: " + " / ".join(last_errors[:3]),
            status_code=502,
        )
