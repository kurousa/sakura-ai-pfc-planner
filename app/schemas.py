from __future__ import annotations

import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator


EquipmentId = Literal[
    "ih_1",
    "gas_2",
    "microwave",
    "oven",
    "cooking_kettle",
    "rice_cooker",
]

EQUIPMENT_LABELS: dict[str, str] = {
    "ih_1": "IHコンロ（1口）",
    "gas_2": "ガスコンロ（2口以上）",
    "microwave": "電子レンジ",
    "oven": "オーブン",
    "cooking_kettle": "クッキングケトル",
    "rice_cooker": "炊飯器",
}

StartTiming = Literal["dinner_start", "breakfast_start"]


class PlanRequest(BaseModel):
    ingredients_text: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="手持ち食材・宅配リストのテキスト",
    )
    target_calories: int = Field(
        default=1650,
        ge=1200,
        le=2800,
        description="1日あたりの目標摂取カロリー (kcal)",
    )
    equipments: list[EquipmentId] = Field(
        default_factory=lambda: ["ih_1", "microwave", "oven", "cooking_kettle"],
        min_length=1,
        description="使用可能な調理器具IDリスト",
    )
    start_timing: StartTiming = Field(
        default="dinner_start",
        description="開始タイミング（お届け日夕食スタート or 1日目朝食スタート）",
    )

    @field_validator("ingredients_text")
    @classmethod
    def strip_ingredients(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 5:
            raise ValueError("食材リストは5文字以上で入力してください。")
        return cleaned


class MealItem(BaseModel):
    slot: Literal["朝食", "昼食", "夕食"]
    name: str = Field(..., min_length=1)
    used_ingredients: list[str] = Field(..., min_length=1)
    equipments: list[str] = Field(..., min_length=1)
    calories_kcal: int = Field(..., ge=50, le=1800)
    protein_g: float = Field(..., ge=0, le=150)
    fat_g: float = Field(..., ge=0, le=80)
    carbs_g: float = Field(..., ge=0, le=250)
    steps: list[str] = Field(..., min_length=1, max_length=6)


class DayPlan(BaseModel):
    day: int = Field(..., ge=1, le=8)
    label: str = Field(..., min_length=1)
    meals: list[MealItem] = Field(..., min_length=1, max_length=3)
    daily_calories_kcal: int = Field(..., ge=200, le=3500)
    daily_protein_g: float = Field(..., ge=0, le=300)
    daily_fat_g: float = Field(..., ge=0, le=150)
    daily_carbs_g: float = Field(..., ge=0, le=500)


class IngredientUsage(BaseModel):
    ingredient: str
    schedule: str


class MealPlanOutput(BaseModel):
    summary: str
    assumptions: list[str] = Field(default_factory=list)
    ingredient_usage: list[IngredientUsage] = Field(default_factory=list)
    days: list[DayPlan] = Field(..., min_length=7, max_length=8)


class PlanResponse(BaseModel):
    plan: MealPlanOutput
    warnings: list[str] = Field(default_factory=list)
    cached: bool = False
    retried: bool = False
    model: str
    monthly_used: int
    monthly_limit: int


MULTI_BURNER_PATTERNS = [
    re.compile(r"別の?(?:鍋|フライパン)で同時"),
    re.compile(r"同時に(?:炒め|焼き|煮|茹で)ながら.*(?:炒め|焼き|煮|茹で)"),
    re.compile(r"2口|二口|コンロを2つ"),
]


def normalize_daily_totals(plan: MealPlanOutput) -> MealPlanOutput:
    """LLMの足し算ミスを防ぐため、各日の合計カロリー・PFCを各食の合算値で補正する。"""
    for day in plan.days:
        day.daily_calories_kcal = sum(m.calories_kcal for m in day.meals)
        day.daily_protein_g = round(sum(m.protein_g for m in day.meals), 1)
        day.daily_fat_g = round(sum(m.fat_g for m in day.meals), 1)
        day.daily_carbs_g = round(sum(m.carbs_g for m in day.meals), 1)
    return plan


def validate_plan_constraints(
    plan: MealPlanOutput,
    request: PlanRequest,
) -> tuple[list[str], list[str]]:
    """調理器具制約・食数・PFCレンジを機械検証し、(hard_violations, soft_warnings) を返す。

    - hard_violations: 物理的に調理不可能な制約違反（自己修正リトライ対象）
    - soft_warnings: 栄養バランス等のズレ（レシピは捨てず、UI上に警告バナー表示）
    """
    hard_violations: list[str] = []
    soft_warnings: list[str] = []

    allowed_labels = {EQUIPMENT_LABELS[eq] for eq in request.equipments}
    allowed_tokens = set(request.equipments) | allowed_labels | {"包丁・ボウルのみ", "火不要", "調理不要", "常温"}
    is_single_burner = "ih_1" in request.equipments and "gas_2" not in request.equipments

    total_meals = sum(len(d.meals) for d in plan.days)
    if total_meals < 18 or total_meals > 24:
        soft_warnings.append(f"合計食数が {total_meals} 食です（目安：7日間・計21食）。必要に応じて調整してください。")

    for day in plan.days:
        for meal in day.meals:
            # 1口IH制約の同時調理チェック（物理制約：ハード違反）
            if is_single_burner:
                joined_steps = " ".join(meal.steps)
                for pat in MULTI_BURNER_PATTERNS:
                    if pat.search(joined_steps):
                        hard_violations.append(
                            f"Day {day.day} {meal.slot}『{meal.name}』で1口IH制約に反する同時コンロ調理が検出されました。"
                        )
                        break

            # 未選択器具の混入チェック（物理制約：ハード違反）
            eq_text = " ".join(meal.equipments)
            if "oven" not in request.equipments and "オーブン" in eq_text:
                hard_violations.append(f"Day {day.day} {meal.slot}『{meal.name}』で未選択のオーブンが使用されています。")
            if "cooking_kettle" not in request.equipments and "ケトル" in eq_text:
                hard_violations.append(f"Day {day.day} {meal.slot}『{meal.name}』で未選択のクッキングケトルが使用されています。")
            if "rice_cooker" not in request.equipments and "炊飯器" in eq_text:
                hard_violations.append(f"Day {day.day} {meal.slot}『{meal.name}』で未選択の炊飯器が使用されています。")
            if "microwave" not in request.equipments and "電子レンジ" in eq_text:
                hard_violations.append(f"Day {day.day} {meal.slot}『{meal.name}』で未選択の電子レンジが使用されています。")

            # 許可トークン以外の未知器具が混ざった場合はソフト警告
            if not any(tok in eq_text or eq_text in tok for tok in allowed_tokens):
                soft_warnings.append(
                    f"Day {day.day} {meal.slot}『{meal.name}』の器具表記（{eq_text}）を確認してください。"
                )

        # フル日（3食ある日）のカロリー・脂質チェック（レシピ破棄せずソフト警告で通知）
        if len(day.meals) == 3:
            if day.daily_calories_kcal < request.target_calories - 550:
                soft_warnings.append(
                    f"Day {day.day} の推定カロリー（{day.daily_calories_kcal} kcal）が目標（{request.target_calories} kcal）より低めです。主食やプロテイン等で補給してください。"
                )
            elif day.daily_calories_kcal > request.target_calories + 550:
                soft_warnings.append(
                    f"Day {day.day} の推定カロリー（{day.daily_calories_kcal} kcal）が目標（{request.target_calories} kcal）より高めです。主食量で調整してください。"
                )
            if day.daily_fat_g > 70:
                soft_warnings.append(
                    f"Day {day.day} の推定脂質（{day.daily_fat_g}g）が高めです（目安60g以下）。油や食材の量で調整してください。"
                )

    return hard_violations, soft_warnings
