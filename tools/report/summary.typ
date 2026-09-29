#let c-header = gray.lighten(40%)

#let fmt-percent(numerator, denominator) = {
  if denominator == 0 { "0%" } else {
    str(calc.round(decimal(numerator * 100 / denominator), digits: 1)) + "%"
  }
}

// --- Cell Components ---

#let cell-model(model, icon: auto) = {
  let _icon = if icon == auto {
    if model.starts-with("claude") {
      image("icons/claude.svg")
    } else if model.starts-with("gpt") {
      image("icons/openai.svg")
    } else {
      [u]
    }
  } else {
    [u]
  }

  table.cell[#box(_icon) #model]
}

// --- Main Report Function ---

#let summary-table(rows) = {
  let headers = (
    "Model",
    "Agent",
    [Spend #footnote[The reported "spend" values are estimates derived from usage metrics exposed by our LLM proxy, and should not be interpreted as exact billing records. Commercial LLM providers apply their own server-side caching and other optimizations that can reduce the actually billed usage relative to the nominal token consumption seen at the proxy, but detailed information about cache hits and final charges is only available via the providers' raw billing and usage APIs, which we do not query in this report.]],
    "Time",
    "Build",
    "PoC",
    "Func",
    "Intent",
  ).map(t => table.cell(fill: c-header)[*#t*])

  table(
    columns: 8,
    align: (col, row) => (
      (if row != 0 and col == 0 { left } else { center }) + horizon
    ),
    ..headers,
    ..rows.flatten(),
  )
}

#let summary-row(model: none, agent: none, results: ()) = {
  if results == none or results.len() == 0 {
    return
  }

  let count = results.len()
  let avg-time = results.map(r => r.runtime_result.agent_duration).sum() / count
  let avg-spend = results.map(r => r.spend).sum() / count

  let count-true(pred) = results.filter(pred).len()

  let pct-build = count-true(r => r.patch_result.build_success == true)
  let pct-poc = count-true(r => (
    r.patch_result.pov_passed == r.patch_result.pov_total
  ))
  let pct-func = count-true(r => r.patch_result.func_test_success == true)
  let pct-intent = count-true(r => (
    r.patch_result.intent_test_success == true
  ))

  (
    cell-model(model),
    agent,
    [\$#calc.round(decimal(avg-spend), digits: 2)],
    [#calc.round(decimal(avg-time / 60), digits: 1) min],
    [*#fmt-percent(pct-build, count)*],
    [*#fmt-percent(pct-poc, count)*],
    [*#fmt-percent(pct-func, count)*],
    [*#fmt-percent(pct-intent, count)*],
  ).map(t => table.cell(fill: auto)[#t])
}
