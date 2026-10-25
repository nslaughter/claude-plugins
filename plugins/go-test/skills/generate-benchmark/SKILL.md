---
name: generate-benchmark
description: Scaffold Benchmark functions with ResetTimer, ReportAllocs, sub-benchmarks for input sizes, and comparison patterns. Use when the user asks to benchmark, profile, or measure the performance of a Go function.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Generate Benchmark

Scaffold `Benchmark*` functions for Go code with proper timer management, allocation reporting, sub-benchmarks for varying input sizes, and comparison benchmarks when applicable.

## Step 1 -- Identify the Target Function

Follow the [target identification procedure](../_common/references/target-identification.md) with:
- **skill-purpose**: benchmarks
- **candidate-guidance**: exported functions, especially performance-sensitive ones

The user may request benchmarks for multiple functions at once. Process each function through the steps below.

## Step 2 -- Evaluate Whether a Benchmark Is the Right Approach

Read the code under test and evaluate whether a benchmark is the best fit. See [test type decision matrix](../_common/references/test-type-decision-matrix.md) for the full cross-reference.

### BAD candidates for benchmarks -- recommend alternatives instead

| Subject | Why Benchmarks Are Wrong | Recommend Instead |
|---|---|---|
| Functions with external I/O (DB, network, disk) without isolation | Benchmark results will be dominated by I/O latency, not the code's performance. Isolate dependencies first, or benchmark only the computation. | **Mocks** to isolate -- offer `/generate-mocks`, then benchmark |
| Functions that aren't yet correct | Benchmarking incorrect code measures the speed of wrong answers. Get correctness tests passing first. | **Table tests** -- offer `/generate-table-tests` |
| Functions you haven't profiled yet | You may be benchmarking the wrong function. Profile first to find the actual bottleneck. | `go test -cpuprofile` / `go tool pprof` -- explain workflow |

If the subject matches a BAD row above, redirect the user using this pattern:

> "Benchmark tests measure performance characteristics like ns/op and allocations. For [this code's characteristics], [alternative](/generate-alternative) is a better fit because [reason]. Would you like to switch?"

If borderline, use `AskUserQuestion` with the recommended alternative as the first option and "Proceed with benchmark" as the second.

## Step 3 -- Analyze the Function

Read the file containing the target function. Extract:

1. **Function signature**: parameters, return types, receiver (if method).
2. **Input characteristics**: what constitutes a "small" vs "large" input for this function (e.g., string length, slice size, map entries, file size).
3. **Setup requirements**: does the function need a database connection, file handle, initialized struct, or other expensive setup that should be done outside the benchmark loop?
4. **Side effects**: does the function write to disk, allocate large buffers, or perform I/O? These affect benchmark design.
5. **Package name** and required imports.

Also check for related functions that suggest a **comparison benchmark**:

- An older/newer version of the same function (e.g., `ParseV1` vs `ParseV2`).
- A stdlib alternative (e.g., `json.Unmarshal` vs a custom parser).
- A function with and without a cache or optimization.
- The same function with different configuration options.

Search for these patterns:

Use Grep to search for functions with similar names in the source file.

## Step 4 -- Determine Benchmark Variants

Based on the analysis, decide which benchmark variants to generate:

### Basic Benchmark (always generated)
A straightforward `b.N` loop calling the function with a representative input.

### Sub-benchmarks by Input Size (generate when applicable)
When the function's performance varies with input size, generate sub-benchmarks:

| Function Type | Input Size Variants |
|---|---|
| String processing | `10B`, `100B`, `1KB`, `10KB`, `100KB` |
| Slice operations | `10`, `100`, `1000`, `10000` elements |
| Map operations | `10`, `100`, `1000` entries |
| I/O operations | `1KB`, `10KB`, `100KB`, `1MB` |
| Numeric computation | `small`, `medium`, `large` (domain-specific) |

### Comparison Benchmark (generate when a baseline exists)
When a comparison function was found in Step 2, generate a benchmark that tests both side by side using sub-benchmarks.

### Allocation Benchmark (always included)
Every benchmark includes `b.ReportAllocs()` so allocation counts appear in results.

## Step 5 -- Generate the Benchmark File

Generate the benchmark in the same package. Name the file `<source>_bench_test.go` (e.g., `parser_bench_test.go`). If the file already exists, append to it using the Edit tool.

### Basic Benchmark Template

```go
func Benchmark<FunctionName>(b *testing.B) {
    // Setup: create inputs and any required state outside the loop.
    input := <representative_input>

    b.ReportAllocs()
    b.ResetTimer()
    for b.Loop() {
        <FunctionName>(input)
    }
}
```

Important patterns to follow:

- Use `b.ReportAllocs()` in every benchmark.
- Always call `b.ResetTimer()` immediately before the benchmark loop, even when there is no setup to exclude from timing. This ensures consistent, reproducible results and is required regardless of whether setup exists.
- Use `b.Loop()` for the benchmark loop (preferred pattern when the project's Go version supports it) instead of `for i := 0; i < b.N; i++`. Check the project's `go.mod` to determine which loop pattern to use:

Use Grep to search for `^go ` in `go.mod` to check the Go version.

- Assign results to a package-level variable or use `b.StopTimer()`/`b.StartTimer()` to prevent the compiler from optimizing away the call. Prefer the sink variable approach:

```go
var benchResult <return_type>

func Benchmark<FunctionName>(b *testing.B) {
    input := <representative_input>
    var r <return_type>
    b.ReportAllocs()
    b.ResetTimer()
    for b.Loop() {
        r, _ = <FunctionName>(input)
    }
    benchResult = r
}
```

### Sub-benchmark Template (varying input sizes)

```go
func Benchmark<FunctionName>(b *testing.B) {
    sizes := []struct {
        name string
        input <input_type>
    }{
        {"10B", <generate_input_of_size_10>},
        {"100B", <generate_input_of_size_100>},
        {"1KB", <generate_input_of_size_1000>},
        {"10KB", <generate_input_of_size_10000>},
    }

    for _, sz := range sizes {
        b.Run(sz.name, func(b *testing.B) {
            b.ReportAllocs()
            b.ResetTimer()
            for b.Loop() {
                <FunctionName>(sz.input)
            }
        })
    }
}
```

### Comparison Benchmark Template

```go
func Benchmark<FunctionName>Comparison(b *testing.B) {
    input := <representative_input>

    b.Run("current", func(b *testing.B) {
        b.ReportAllocs()
        b.ResetTimer()
        for b.Loop() {
            <FunctionName>(input)
        }
    })

    b.Run("baseline", func(b *testing.B) {
        b.ReportAllocs()
        b.ResetTimer()
        for b.Loop() {
            <BaselineFunction>(input)
        }
    })
}
```

### Method Benchmarks

If the function is a method, construct the receiver outside the loop:

```go
func Benchmark<TypeName>_<MethodName>(b *testing.B) {
    obj := &<TypeName>{/* valid initialization */}
    input := <representative_input>

    b.ReportAllocs()
    b.ResetTimer()
    for b.Loop() {
        obj.<MethodName>(input)
    }
}
```

## Step 6 -- Add Input Generation Helpers

If sub-benchmarks need generated input of specific sizes, add helper functions:

```go
func generateStringOfSize(n int) string {
    b := make([]byte, n)
    for i := range b {
        b[i] = 'a' + byte(i%26)
    }
    return string(b)
}

func generateSliceOfSize[T any](n int, factory func(i int) T) []T {
    s := make([]T, n)
    for i := range s {
        s[i] = factory(i)
    }
    return s
}
```

Only include helpers that are actually used by the generated benchmarks.

## Step 7 -- Write the File

Write the generated benchmark file. Before writing:

1. Check if the target file already exists.
2. If it does and contains a `Benchmark<FunctionName>` function, warn the user and ask whether to overwrite or generate with a different name.
3. If it exists but has no naming conflict, append the new benchmark function.

Run `gofmt` on the generated file:

```bash
gofmt -w <test_file_path>
```

## Step 8 -- Verify and Run

Verify the benchmark compiles and run it once:

```bash
cd <package_directory> && go test -bench "Benchmark<FunctionName>" -benchtime=1s -count=1 ./... 2>&1
```

If compilation fails, read the error, fix the generated code, and re-run.

## Step 9 -- Present Results

Report to the user:

1. The path to the generated benchmark file.
2. Which benchmark variants were generated (basic, sub-benchmarks, comparison) and why.
3. The output from the initial benchmark run.
4. Any `TODO` items (e.g., "Add a comparison function for before/after optimization").

Include usage guidance:

```
# Run benchmarks
go test -bench Benchmark<FunctionName> -benchtime=3s -count=5 ./path/to/package

# Compare results across runs (install benchstat: go install golang.org/x/perf/cmd/benchstat@latest)
go test -bench Benchmark<FunctionName> -count=10 ./path/to/package > old.txt
# ... make changes ...
go test -bench Benchmark<FunctionName> -count=10 ./path/to/package > new.txt
benchstat old.txt new.txt

# Profile CPU
go test -bench Benchmark<FunctionName> -cpuprofile=cpu.prof ./path/to/package
go tool pprof cpu.prof

# Profile memory
go test -bench Benchmark<FunctionName> -memprofile=mem.prof ./path/to/package
go tool pprof mem.prof
```
