const SAMPLE_INGREDIENTS = `【冷蔵】
・緑豆もやし 300g
・ほうとう鍋セット 2〜3人分
・プレーンヨーグルト（低脂肪） 400g
・もめん豆腐（小分け） 150g×2
・小粒納豆 30g×4
【青果】
・バナナ 5本
・ミニトマト 130g
・カットキャベツ 1/2カット
・きのこセット（しめじ・えのき等） 1パック
・玉ねぎ 3個
・人参 2本
【冷凍】
・鶏ムネ肉 350g
・味付き豚ロース（醤油味） 270g
・冷凍チャーハン 230g×2
【常温】
・さば水煮缶 150g×3
・パックごはん 200g×10`;

let latestPlan = null;

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderPlan(resp) {
  latestPlan = resp.plan;
  const plan = resp.plan;

  document.getElementById("resultSection").classList.remove("hidden");
  document.getElementById("metaInfo").textContent =
    `モデル: ${resp.model} ｜ ${resp.cached ? "⚡ キャッシュ返却（無料枠消費なし）" : "🆕 新規生成"}` +
    (resp.retried ? " ｜ 🔁 制約自動修正リトライ実施" : "");
  document.getElementById("summaryText").textContent = plan.summary;

  const assumptionsEl = document.getElementById("assumptionsList");
  assumptionsEl.innerHTML = (plan.assumptions || [])
    .map((a) => `<li>${escapeHtml(a)}</li>`)
    .join("");

  const warningBox = document.getElementById("warningBox");
  const warningList = document.getElementById("warningList");
  const warnings = resp.warnings || [];
  if (warnings.length > 0) {
    warningList.innerHTML = warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("");
    warningBox.classList.remove("hidden");
  } else {
    warningList.innerHTML = "";
    warningBox.classList.add("hidden");
  }

  const daysEl = document.getElementById("tabDays");
  daysEl.innerHTML = plan.days
    .map((d) => {
      const mealsHtml = d.meals
        .map(
          (m) => `
          <div class="border border-slate-200 rounded-lg p-3.5 bg-slate-50/60 space-y-2">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="font-semibold text-slate-900">
                <span class="inline-block text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded mr-1.5">${escapeHtml(m.slot)}</span>
                ${escapeHtml(m.name)}
              </div>
              <div class="text-xs font-medium text-slate-600">
                ${m.calories_kcal} kcal（P:${m.protein_g}g / F:${m.fat_g}g / C:${m.carbs_g}g）
              </div>
            </div>
            <div class="flex flex-wrap gap-1.5">
              ${m.equipments
                .map(
                  (eq) =>
                    `<span class="text-xs bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded-full">🔧 ${escapeHtml(eq)}</span>`
                )
                .join("")}
            </div>
            <div class="text-xs text-slate-600">
              <strong>使用食材:</strong> ${m.used_ingredients.map(escapeHtml).join("、")}
            </div>
            <ol class="text-xs text-slate-700 list-decimal pl-5 space-y-0.5">
              ${m.steps.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}
            </ol>
          </div>
        `
        )
        .join("");

      return `
        <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-5 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2">
            <h3 class="font-bold text-slate-900">${escapeHtml(d.label)}</h3>
            <span class="text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full">
              合計 ${d.daily_calories_kcal} kcal ｜ P:${d.daily_protein_g}g / F:${d.daily_fat_g}g / C:${d.daily_carbs_g}g
            </span>
          </div>
          <div class="space-y-3">${mealsHtml}</div>
        </div>
      `;
    })
    .join("");

  const usageEl = document.getElementById("tabUsage");
  if (plan.ingredient_usage && plan.ingredient_usage.length > 0) {
    usageEl.innerHTML = `
      <table class="w-full text-sm text-left border-collapse">
        <thead>
          <tr class="border-b border-slate-200 text-slate-600">
            <th class="py-2 pr-4">食材</th>
            <th class="py-2">消費スケジュール</th>
          </tr>
        </thead>
        <tbody>
          ${plan.ingredient_usage
            .map(
              (u) => `
              <tr class="border-b border-slate-100">
                <td class="py-2 pr-4 font-medium text-slate-800">${escapeHtml(u.ingredient)}</td>
                <td class="py-2 text-slate-600">${escapeHtml(u.schedule)}</td>
              </tr>
            `
            )
            .join("")}
        </tbody>
      </table>
    `;
  } else {
    usageEl.innerHTML = `<p class="text-sm text-slate-500">食材消費マップ情報はありません。</p>`;
  }
}

function planToMarkdown(plan) {
  const lines = ["# 7日間PFC献立プラン", "", plan.summary, ""];
  if (plan.ingredient_usage && plan.ingredient_usage.length > 0) {
    lines.push("## 食材使い切りマップ", "", "| 食材 | 消費スケジュール |", "| :--- | :--- |");
    for (const u of plan.ingredient_usage) {
      lines.push(`| ${u.ingredient} | ${u.schedule} |`);
    }
    lines.push("");
  }
  lines.push("## 日別献立・手順", "");
  for (const d of plan.days) {
    lines.push(
      `### ${d.label}（${d.daily_calories_kcal} kcal / P:${d.daily_protein_g}g F:${d.daily_fat_g}g C:${d.daily_carbs_g}g）`
    );
    for (const m of d.meals) {
      lines.push(
        `- **${m.slot}：${m.name}**（${m.calories_kcal} kcal / P:${m.protein_g}g F:${m.fat_g}g C:${m.carbs_g}g）`
      );
      lines.push(`  - 器具: ${m.equipments.join("、")}`);
      lines.push(`  - 食材: ${m.used_ingredients.join("、")}`);
      m.steps.forEach((s, idx) => lines.push(`  ${idx + 1}. ${s}`));
    }
    lines.push("");
  }
  return lines.join("\n");
}

document.getElementById("sampleBtn").addEventListener("click", () => {
  document.getElementById("ingredients").value = SAMPLE_INGREDIENTS;
});

document.getElementById("generateBtn").addEventListener("click", async () => {
  const errorBox = document.getElementById("errorBox");
  const loadingMsg = document.getElementById("loadingMsg");
  const btn = document.getElementById("generateBtn");

  errorBox.classList.add("hidden");
  const ingredients_text = document.getElementById("ingredients").value.trim();
  const target_calories = Number(document.getElementById("calories").value) || 1650;
  const start_timing = document.getElementById("startTiming").value;
  const equipments = Array.from(
    document.querySelectorAll('input[name="equipments"]:checked')
  ).map((el) => el.value);

  if (ingredients_text.length < 5) {
    errorBox.textContent = "食材リストを5文字以上で入力してください（サンプルボタンも利用できます）。";
    errorBox.classList.remove("hidden");
    return;
  }
  if (equipments.length === 0) {
    errorBox.textContent = "使用可能な調理器具を1つ以上選択してください。";
    errorBox.classList.remove("hidden");
    return;
  }

  btn.disabled = true;
  loadingMsg.classList.remove("hidden");

  try {
    const res = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ingredients_text,
        target_calories,
        equipments,
        start_timing,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || `エラーが発生しました (HTTP ${res.status})`);
    }
    renderPlan(data);
  } catch (err) {
    errorBox.textContent = err.message || "通信エラーが発生しました。";
    errorBox.classList.remove("hidden");
  } finally {
    btn.disabled = false;
    loadingMsg.classList.add("hidden");
  }
});

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.remove("border-indigo-600", "text-indigo-600");
      b.classList.add("border-transparent", "text-slate-500");
    });
    btn.classList.add("border-indigo-600", "text-indigo-600");
    btn.classList.remove("border-transparent", "text-slate-500");

    document.getElementById("tabDays").classList.toggle("hidden", tab !== "days");
    document.getElementById("tabUsage").classList.toggle("hidden", tab !== "usage");
  });
});

document.getElementById("copyMdBtn").addEventListener("click", async () => {
  if (!latestPlan) return;
  await navigator.clipboard.writeText(planToMarkdown(latestPlan));
  const btn = document.getElementById("copyMdBtn");
  const prev = btn.textContent;
  btn.textContent = "✅ コピーしました";
  setTimeout(() => (btn.textContent = prev), 2000);
});
