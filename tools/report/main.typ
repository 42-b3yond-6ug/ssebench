#import "summary.typ": summary-row, summary-table
#import "task-table.typ": task-table

#let case_result_json_file = sys.inputs.at(
  "result",
  default: "result.json",
)

#let preset = sys.inputs.at(
  "preset",
  default: "default",
)

// Reference runs apply each task's known fix, so their grades rate the tasks,
// not a model; they are never scored.
// A run with the status `error` was not graded, or its agent failed without the
// model answering a call: it says nothing about the model, so it is listed but
// never scored.
#let all-results = json(case_result_json_file)
#let model-runs = all-results.filter(r => not r.config.at("reference_run", default: false))
#let reference-runs = all-results.len() - model-runs.len()
#let is-error(r) = r.patch_result.at("status", default: none) == "error"
#let error-runs = model-runs.filter(r => is-error(r))
#let results = model-runs.filter(r => not is-error(r))

#grid(
  columns: (auto, 1fr, auto),
  align: horizon,
  [
    #grid(
      rows: 3,
      row-gutter: 12pt,
      text(size: 20pt, weight: "black")[SSEBench Report],
      datetime.today().display("[month repr:long] [day], [year]"),
      [Prepared by _Cybersecurity Reasoning System \@ B3yond_],
    )
  ],
  [],
  image("b3yond.png", width: 100pt),
)

#line(length: 100%)

#let models = results.map(r => r.config.model).dedup()
#let agents = results.map(r => r.config.agent).dedup()
#let tasks = results.map(r => r.task.id).dedup()
#let models_agents = models.map(x => agents.map(y => (x, y))).sum(default: ())

SSEBench is a comprehensive benchmark for evaluating the security capabilities
of language models and agents.
It provides a wide range of vulnerability-related tasks and scenarios
to test the reliability of AI systems in handling security challenges.

This report is automatically generated
by evaluating #(agents.len()) agents (#agents.join(", "))
using #models.len() large language models (#models.join(", "))
over #tasks.len() testcases.
#if reference-runs > 0 [
  #reference-runs reference runs, which apply the known fix of each task
  instead of a model's patch, are left out.
]

#if error-runs.len() > 0 [
  #error-runs.len() runs ended in an error and are left out of the scores,
  since they say nothing about the model:
  #list(..error-runs.map(r => [
    #r.task.id, #r.config.model, #r.config.agent:
    #r.patch_result.at("error_msg", default: none)
  ]))
]

#if results.any(r => r.at("trials", default: 1) > 1) [
  Every run is included: a task that ran more than once for the same model and
  agent has a row for each run, and each run counts as a sample of its own.
  Percentages are shares of runs.
]

#line(length: 100%)

== Summary

#let rows = models_agents.map(p => {
  let model = p.at(0)
  let agent = p.at(1)

  let subset = results.filter(r => (
    r.config.model == model and r.config.agent == agent
  ))
  summary-row(model: model, agent: agent, results: subset)
})

#summary-table(rows.filter(r => r != none))


#pagebreak()

== Benchmark Results

#for model in models {
  for agent in agents {
    let subset = results.filter(r => (
      r.config.model == model and r.config.agent == agent
    ))
    if subset.len() > 0 {
      [
        === #model, #agent
        #columns(if preset == "anonymous" { 2 } else { 1 })[
          #task-table(results: subset, preset: preset)]
      ]
    }
  }
}
