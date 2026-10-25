# Parallelism Convention for Generated Tests

## Default Rule

Every generated `Test*` function calls `t.Parallel()` as its first statement. Every `t.Run` subtest calls `t.Parallel()` as its first line.

For table-driven tests using `for _, tt := range tests`, the loop variable is per-iteration in Go 1.22+ and no re-binding is needed. For projects with `go.mod` specifying a version earlier than 1.22, add `tt := tt` before `t.Run` to capture the loop variable.

## Exceptions -- Do NOT Add `t.Parallel()`

| Exception | Why | Example |
|---|---|---|
| Tests using shared mutable state (package-level vars, shared temp dirs) | Parallel execution causes data races on shared state | Tests that write to a shared `testDB` variable |
| Tests that call `t.Setenv()` | `t.Setenv` panics if called in a parallel test | `t.Setenv("HOME", tmpDir)` |
| Tests that use `os.Chdir` | Process-global state, not goroutine-safe | Any test changing working directory |
| Adversarial concurrency-stress subtests | These deliberately race goroutines against each other; outer parallelism adds noise | `t.Run("concurrency", ...)` in adversarial tests |
| Benchmark functions (`Benchmark*`) | Benchmarks have their own parallelism model via `b.RunParallel` | N/A |
| Fuzz functions (`Fuzz*`) | The fuzz engine manages its own parallelism | N/A |
| txtar/testscript tests | `testscript.Run` manages parallel execution via `testscript.Params.Parallel` | N/A |
| Tests with explicit ordering dependencies | When test B must run after test A completes | Sequential integration test chains |

## Go Version Note

Check the project's `go.mod` to determine the Go version:

- **Go 1.22+**: Loop variables are per-iteration. Use `for _, tt := range tests` directly -- no `tt := tt` needed.
- **Before Go 1.22**: Add `tt := tt` immediately before `t.Run` inside table-driven loops to capture the loop variable for the subtest closure.

Skills should check `go.mod` and apply the appropriate pattern.
