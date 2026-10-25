---
name: compare-benchmarks
description: Run benchmarks on two git states and compare with benchstat for statistically significant performance differences. Use when the user asks to compare performance across commits, branches, or before/after a change.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Glob, Grep, AskUserQuestion
---

# Compare Benchmarks

Run benchmarks on two git states (commits, branches, or working tree vs ref), compare results with `benchstat`, and report statistically significant regressions and improvements.

## Step 1 -- Determine Git Refs and Target Package

Determine the two states to compare from the user's prompt:

- **Two refs**, e.g. `main vs feature-branch` or `v1.2.0 vs v1.3.0`: the first is "before" and the second is "after".
- **One ref**, e.g. `compare against main`: that ref is "before", and the working tree as it is now is "after".
- **No refs**: "before" is `HEAD~1` and "after" is the working tree. Confirm with the user: "I'll compare the current code against the previous commit (`HEAD~1`). Want to compare against a different ref?"

Determine the target package, which is benchmarked in both states:

- **A package path**, e.g. `./internal/parser`: use it.
- **A file**, e.g. `parser.go`: the package containing it.
- **A function name**: search for `^func .*FunctionName` in `*.go` files with the Grep tool, then for `func \(.*\) FunctionName` if it's a method, and use the package containing it. If several match, ask which one.
- **Nothing**: ask the user: "Which package should I benchmark? You can give a package path (e.g., `./internal/...`), a file, a function name, or `.` for the current directory."

Confirm the plan with the user before proceeding: "I'll compare benchmarks in `<package>` between `<before>` and `<after>`. Proceed?"

## Step 2 -- Verify benchstat Is Installed

Check for `benchstat`:

```bash
which benchstat 2>&1
```

- If found, proceed normally.
- If not found, inform the user: "`benchstat` is not installed. It provides statistical comparison of benchmark results. Install with: `go install golang.org/x/perf/cmd/benchstat@latest`. Without it, I can still run benchmarks on both states and show raw output for manual comparison. Proceed without benchstat?"

## Step 3 -- Check for Benchmarks

Search for benchmark functions in the target package using the Grep tool: search for `^func Benchmark` in `*_test.go` files under the target path.

- If benchmarks exist, list them. Ask which to compare or offer to compare all.
- If no benchmarks exist: "No benchmarks found in `<package>`. You can create benchmarks with `/generate-benchmark`, or write them by hand, then re-run `/compare-benchmarks`."

## Step 4 -- Run Benchmarks on "Before" State

Check out the "before" ref in a worktree of its own, so the user's working tree, branch, and uncommitted changes are never touched. Create a temporary directory:

```bash
mktemp -d
```

Use the path it prints as `<before_dir>`:

```bash
git worktree add --detach <before_dir> <before_ref>
```

Run the benchmarks there with `-count=6` for statistical significance:

```bash
cd <before_dir>/<package_dir> && go test -bench=<pattern> -benchmem -count=6 -timeout=300s . 2>&1 | tee /tmp/bench-before.txt
```

Record the benchmark output. Use `-count=6` minimum -- `benchstat` needs multiple runs to compute p-values. Then remove the worktree:

```bash
git worktree remove --force <before_dir>
```

## Step 5 -- Run Benchmarks on "After" State

If "after" is the working tree, run the benchmarks in the repository as it is, with the same settings:

```bash
cd <package_dir> && go test -bench=<pattern> -benchmem -count=6 -timeout=300s . 2>&1 | tee /tmp/bench-after.txt
```

If "after" is a ref, check it out in a second worktree the same way as in Step 4, run the same command there with its output going to `/tmp/bench-after.txt`, and remove the worktree.

## Step 6 -- Compare with benchstat

If `benchstat` is available:

```bash
benchstat /tmp/bench-before.txt /tmp/bench-after.txt 2>&1
```

Parse the benchstat output. For each benchmark, extract:
- **Name**: the benchmark function name
- **Before**: old ns/op, B/op, allocs/op
- **After**: new ns/op, B/op, allocs/op
- **Delta**: percentage change with confidence interval
- **p-value**: statistical significance (p < 0.05 is significant)

If `benchstat` is not available, present raw before/after numbers side by side.

## Step 7 -- Compile Report

Categorize results into regressions, improvements, and no change:

```
## Benchmark Comparison: <before> vs <after>

### Summary
- Benchmarks compared: N
- Regressions: N
- Improvements: N
- No significant change: N

### Regressions (performance got worse)

| Benchmark | Before | After | Delta | p-value |
|---|---|---|---|---|
| BenchmarkParse | 1,234 ns/op | 2,456 ns/op | +99.0% | p=0.002 |
| BenchmarkParse | 5 allocs/op | 12 allocs/op | +140% | p=0.001 |

### Improvements (performance got better)

| Benchmark | Before | After | Delta | p-value |
|---|---|---|---|---|
| BenchmarkEncode | 5,678 ns/op | 2,345 ns/op | -58.7% | p=0.001 |

### No Significant Change

| Benchmark | Before | After | Delta | p-value |
|---|---|---|---|---|
| BenchmarkLookup | 123 ns/op | 125 ns/op | ~ | p=0.423 |
```

Highlight any results where the p-value is borderline (0.05 < p < 0.10) and recommend running with higher count for more confidence.

## Step 8 -- Clean Up and Cross-Reference

Remove temporary benchmark files:

```bash
rm -f /tmp/bench-before.txt /tmp/bench-after.txt
```

If a run was interrupted, `git worktree list` shows any worktree left from Steps 4 and 5; remove it with `git worktree remove --force <dir>`.

Suggest next steps based on results:

- If regressions found: "To understand what caused the regression, profile the slower benchmarks: `go test -bench=<name> -cpuprofile=cpu.out`, then `go tool pprof -top cpu.out` shows which code paths got more expensive."
- If improvements confirmed: "The optimization is statistically significant. Consider adding these benchmarks to CI to prevent future regressions."
- If results are noisy (high p-values): "Results are not statistically significant. Try running with `-count=10` for more samples, or ensure the machine has minimal background load."
- If memory regressions: "Memory usage increased. Profile the slower benchmarks with `go test -bench=<name> -memprofile=mem.out`, then `go tool pprof -sample_index=alloc_space -top mem.out` shows the new allocation sites."
