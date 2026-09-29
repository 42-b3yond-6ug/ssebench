#import "@preview/digestify:0.1.0": *

// --- Constants & Styling ---
#let c-pass = rgb("e6ffe6") // Light Green
#let c-fail = rgb("ffe6e6") // Light Red
#let c-gray = luma(230)
#let c-header = gray.lighten(40%)

// --- Helper Functions ---

#let get-short-hash(task-id, preset: "default") = {
  if preset == "anonymous" {
    let h = bytes-to-hex(sha1(bytes(task-id)))
    h.slice(0, 6)
  } else {
    task-id
  }
}

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
    } else {
      [u]
    }
  } else {
    [u]
  }

  table.cell[#box(_icon) #model]
}

#let cell-status(condition, label: auto) = {
  let (bg, text-content) = if condition == true {
    (c-pass, "Pass")
  } else if condition == false {
    (c-fail, "Fail")
  } else {
    (c-gray, "N/A")
  }

  // Override text if a specific label is provided
  if label != auto { text-content = label }

  table.cell(fill: bg, inset: 4pt)[#text-content]
}

#let cell-time(result) = {
  let stats = result.runtime_result
  let mins = calc.ceil(duration(seconds: stats.agent_duration).minutes())
  let is-timeout = stats.at("agent_timeout", default: false)

  if is-timeout {
    table.cell(fill: c-fail)[_timeout_]
  } else {
    table.cell[#mins\m]
  }
}

#let cell-pov(pr) = {
  cell-status(
    if pr.pov_passed != none { pr.pov_passed == pr.pov_total } else {
      none
    },
    label: if pr.pov_passed != none {
      [#pr.pov_passed / #pr.pov_total]
    } else { auto },
  )
}

#let task-table(results: (), preset: "default") = {
  set text(size: 8pt)

  if results == none or results.len() == 0 {
    return
  }

  // 1. Calculate Statistics for Footer
  let count = results.len()
  let avg-time = results.map(r => r.runtime_result.agent_duration).sum() / count
  let avg-spend = results.map(r => r.spend).sum() / count

  let count-true(pred) = results.filter(pred).len()

  let pct-build = count-true(r => r.patch_result.build_success == true)
  // A run without a PoC result (not graded, or its build failed) stopped none.
  let pct-poc = count-true(r => (
    r.patch_result.pov_total != none
      and r.patch_result.pov_passed == r.patch_result.pov_total
  ))
  let pct-func = count-true(r => r.patch_result.func_test_success == true)
  let pct-intent = count-true(r => (
    r.patch_result.intent_test_success == true
  ))

  // 2. Define Headers and Footer
  let headers = (
    "ID",
    "Spend",
    "Time",
    "Build",
    "PoC",
    "Func",
    "Intent",
  ).map(t => table.cell(fill: c-header)[*#t*])

  let footer = (
    [*Avg*],
    [\$#calc.round(decimal(avg-spend), digits: 2)],
    [#calc.round(decimal(avg-time / 60), digits: 1)\m],
    [*#fmt-percent(pct-build, count)*],
    [*#fmt-percent(pct-poc, count)*],
    [*#fmt-percent(pct-func, count)*],
    [*#fmt-percent(pct-intent, count)*],
  ).map(t => table.cell(fill: c-header)[#t])

  // 3. Render Table
  table(
    columns: 7,
    align: center + horizon,

    table.header(..headers),

    // Map rows
    ..results
      .map(r => {
        let pr = r.patch_result
        (
          get-short-hash(r.task.id, preset: preset),
          [\$#calc.round(decimal(r.spend), digits: 2)],
          cell-time(r),
          cell-status(pr.build_success),
          cell-pov(pr),
          cell-status(pr.func_test_success),
          cell-status(pr.intent_test_success),
        )
      })
      .flatten(),

    table.footer(..footer),
  )
}
