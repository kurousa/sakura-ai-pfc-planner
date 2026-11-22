from app.ai_client import extract_json_text
from app.schemas import (
    DayPlan,
    MealItem,
    MealPlanOutput,
    PlanRequest,
    normalize_daily_totals,
    validate_plan_constraints,
)
from app.storage import Storage


def _make_valid_plan() -> MealPlanOutput:
    meal = MealItem(
        slot="夕食",
        name="鶏ムネ肉ともやしのレンジ蒸し",
        used_ingredients=["鶏ムネ肉", "もやし"],
        equipments=["電子レンジ"],
        calories_kcal=550,
        protein_g=40.0,
        fat_g=10.0,
        carbs_g=65.0,
        steps=["耐熱皿に具材をのせてラップする", "600Wで5分加熱する"],
    )
    days = []
    for d in range(1, 8):
        meals = [
            meal.model_copy(update={"slot": "朝食"}),
            meal.model_copy(update={"slot": "昼食"}),
            meal.model_copy(update={"slot": "夕食"}),
        ]
        days.append(
            DayPlan(
                day=d,
                label=f"Day {d}",
                meals=meals,
                daily_calories_kcal=1650,
                daily_protein_g=120.0,
                daily_fat_g=30.0,
                daily_carbs_g=195.0,
            )
        )
    return MealPlanOutput(summary="高タンパク・低脂質の7日間プラン", days=days)


def test_validate_plan_constraints_pass() -> None:
    req = PlanRequest(
        ingredients_text="鶏ムネ肉 350g、もやし 300g、さば水煮缶 3缶",
        target_calories=1650,
        equipments=["ih_1", "microwave", "oven", "cooking_kettle"],
    )
    plan = _make_valid_plan()
    hard, soft = validate_plan_constraints(plan, req)
    assert hard == []
    assert soft == []


def test_validate_plan_constraints_detects_multi_burner() -> None:
    req = PlanRequest(
        ingredients_text="鶏ムネ肉 350g、もやし 300g",
        target_calories=1650,
        equipments=["ih_1", "microwave"],
    )
    plan = _make_valid_plan()
    plan.days[0].meals[0].steps = ["フライパンで炒めながら別の鍋で同時にスープを煮る"]
    hard, _ = validate_plan_constraints(plan, req)
    assert any("1口IH制約" in v for v in hard)


def test_validate_plan_constraints_detects_unselected_equipment() -> None:
    req = PlanRequest(
        ingredients_text="鶏ムネ肉 350g、もやし 300g",
        target_calories=1650,
        equipments=["ih_1", "microwave"],
    )
    plan = _make_valid_plan()
    plan.days[0].meals[0].equipments = ["オーブン"]
    hard, _ = validate_plan_constraints(plan, req)
    assert any("未選択のオーブン" in v for v in hard)


def test_validate_plan_constraints_calorie_and_fat_are_soft_warnings() -> None:
    req = PlanRequest(
        ingredients_text="鶏ムネ肉 350g、もやし 300g",
        target_calories=1650,
        equipments=["ih_1", "microwave"],
    )
    plan = _make_valid_plan()
    plan.days[0].daily_calories_kcal = 900
    plan.days[0].daily_fat_g = 75.0
    hard, soft = validate_plan_constraints(plan, req)
    assert hard == []
    assert any("推定カロリー" in w for w in soft)
    assert any("推定脂質" in w for w in soft)


def test_normalize_daily_totals_fixes_llm_sum_mismatch() -> None:
    plan = _make_valid_plan()
    plan.days[0].daily_calories_kcal = 999
    plan.days[0].daily_protein_g = 1.0
    normalize_daily_totals(plan)
    assert plan.days[0].daily_calories_kcal == 1650
    assert plan.days[0].daily_protein_g == 120.0


def test_extract_json_text_strips_markdown_fence() -> None:
    raw = '以下が結果です:\n```json\n{"status": "ok"}\n```'
    assert extract_json_text(raw) == '{"status": "ok"}'


def test_storage_cache_and_rate_limit(tmp_path) -> None:
    db = Storage(str(tmp_path / "test.db"))
    req = PlanRequest(ingredients_text="鶏ムネ肉 350g、もやし 300g")
    key = db.build_cache_key(req, "gpt-oss-120b")
    assert db.get_cached_plan(key) is None

    db.save_cached_plan(key, '{"ok": true}', "gpt-oss-120b")
    assert db.get_cached_plan(key) == ('{"ok": true}', "gpt-oss-120b")

    assert db.check_rate_limits("127.0.0.1", monthly_limit=10, ip_daily_limit=2, ip_minute_limit=1) is None
    db.record_usage("127.0.0.1", upstream_calls=1)
    assert db.get_monthly_used() == 1
    assert db.check_rate_limits("127.0.0.1", monthly_limit=10, ip_daily_limit=2, ip_minute_limit=1) is not None
