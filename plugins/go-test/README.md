# go-test

Go test generation covering 8 test types, plus coverage gaps and benchmark comparison. Each generating skill evaluates whether its test type is the right fit for the code under test and redirects to a better alternative when appropriate.

```
/plugin marketplace add nslaughter/claude-plugins
/plugin install go-test@nslaughter
```

## Workflows

| Skill | Description |
|---|---|
| generate-table-tests | Generate table-driven test skeletons with subtests and edge cases inferred from function signatures. |
| generate-adversarial-tests | Generate tests that deliberately probe a function's assumptions, boundary conditions, and undocumented behaviors. |
| generate-benchmark | Scaffold Benchmark functions with ResetTimer, ReportAllocs, sub-benchmarks for input sizes, and comparison patterns. |
| generate-fuzz-target | Generate Fuzz test functions targeting parsing, validation, and deserialization code with corpus seeds. |
| generate-mocks | Generate interface mocks matching the project's existing conventions -- hand-rolled fakes, testify, or mockgen. |
| generate-property-tests | Generate property-based tests using testing/quick that verify invariants over randomly generated inputs. |
| generate-txtar-tests | Generate txtar-based script tests for CLI tools, file-processing commands, and multi-step workflows using testscript. |
| find-coverage-gaps | Run coverage analysis and identify untested code paths prioritized by complexity and change frequency. |
| compare-benchmarks | Run benchmarks on two git states and compare them with benchstat for statistically significant differences. |

## Usage

All skills are user-invocable:

```
/generate-table-tests
/generate-adversarial-tests
/generate-benchmark
/generate-fuzz-target
/generate-mocks
/generate-property-tests
/generate-txtar-tests
/find-coverage-gaps
/compare-benchmarks
```

Each skill prompts for a target function or package if not specified. Skills share common references in `skills/_common/references/` for target identification, test type decision matrix, and parallelism conventions.

`compare-benchmarks` checks out the "before" state in a separate git worktree, so the working tree and any uncommitted changes are left alone. It uses `benchstat` (`go install golang.org/x/perf/cmd/benchstat@latest`) when it's installed, and shows the raw results otherwise.
