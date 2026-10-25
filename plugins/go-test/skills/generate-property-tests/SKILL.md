---
name: generate-property-tests
description: Generate property-based tests using testing/quick that verify invariants over randomly generated inputs. Use when the user asks to test algebraic properties, round-trip invariants, or universal conditions of a Go function.
model: sonnet
context: fork
user-invocable: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion
---

# Generate Property-Based Tests with testing/quick

Generate property-based tests using Go's standard library `testing/quick` package. Property tests verify that invariants hold across many randomly generated inputs rather than checking specific input/output pairs.

## Step 1 -- Identify the Target Function

Follow the [target identification procedure](../_common/references/target-identification.md) with:
- **skill-purpose**: property tests
- **candidate-guidance**: functions with round-trip, idempotency, or algebraic invariants (encode/decode pairs, sort functions, pure transformations)

## Step 2 -- Evaluate Whether Property Testing Is the Right Approach

See [test type decision matrix](../_common/references/test-type-decision-matrix.md) for the full cross-reference of test types and code characteristics.

Read the code under test and classify it. Property-based tests with `testing/quick` verify that **universal invariants** hold across randomly generated inputs. They are powerful for certain categories of code but wasteful or misleading for others.

### GOOD candidates for property tests

Generate property tests if the subject under test matches **any** of these:

| Category | Why Properties Work | Example Invariants |
|---|---|---|
| Encode/decode pairs | Round-trip property: decode(encode(x)) == x | JSON marshal/unmarshal, base64, protobuf, gob |
| Serialization/deserialization | Encode then decode must recover the original value | Custom binary formats, text protocols |
| Sort/order functions | Idempotency: sort(sort(x)) == sort(x). Length preservation. Element preservation. | `sort.Slice` wrappers, custom comparators |
| Pure transformations | Output properties hold for all inputs: length bounds, character set membership, format guarantees | String normalizers, sanitizers, formatters |
| Mathematical functions | Algebraic laws: commutativity, associativity, distributivity, identity elements | Custom numeric types, vector math, matrix ops |
| Parsers with printers | Round-trip: print(parse(s)) == s for valid inputs, or parse(print(v)) == v | URL parsers, DSL parsers, config formats |
| Idempotent operations | f(f(x)) == f(x) | Normalization, canonicalization, deduplication |
| Comparison/equality | Reflexivity, symmetry, transitivity | Custom `Equal()` or `Less()` methods |
| Set/collection operations | Union/intersection laws, membership, cardinality bounds | Custom set types, filter functions |
| Conversion functions | No data loss: convertBack(convert(x)) == x, or weaker: property of output always holds | Unit converters, type coercions |

### BAD candidates for property tests -- recommend alternatives instead

If the subject under test matches any category below, **do not generate property tests**. Inform the user why property testing is not appropriate and recommend the better alternative. Use this phrasing pattern:

> "Property tests verify universal invariants over randomly generated inputs. For [this code's characteristics], [alternative](/generate-alternative) is a better fit because [reason]. Would you like to switch?"

| Subject Under Test | Why Properties Are Wrong | Recommend Instead |
|---|---|---|
| Functions with complex preconditions | `testing/quick` generates uniform random values. Most will violate preconditions, causing the test to exercise only error paths. | **Table-driven tests** with carefully constructed valid inputs -- offer `/generate-table-tests` |
| Stateful / side-effecting code | Properties must be pure assertions. Functions that write to databases, send HTTP requests, or mutate global state cannot be meaningfully verified by "for all random inputs, this holds." | **Integration tests** or **table-driven tests** with mocks -- offer `/generate-table-tests` or `/generate-mocks` |
| CLI tools / file-based workflows | `testing/quick` generates Go values, not files or command-line arguments. | **txtar script tests** -- offer `/generate-txtar-tests` |
| Functions where the only invariant is "does not panic" | This is exactly what fuzz testing does, with smarter input generation and corpus persistence. | **Fuzz targets** -- offer `/generate-fuzz-target` |
| Functions with no meaningful universal invariant | If you cannot state a property beyond "returns the expected output for this input," you need example-based tests. | **Table-driven tests** -- offer `/generate-table-tests` |
| Performance-sensitive code | Property tests run many iterations but measure correctness, not speed. | **Benchmarks** -- offer `/generate-benchmark` |
| Functions taking interfaces with complex contracts | `testing/quick` cannot generate meaningful interface implementations. It produces nil interfaces or requires custom `Generate` methods that are as complex as the test itself. | **Table-driven tests** with hand-built implementations -- offer `/generate-table-tests` |
| Functions with very large input spaces and narrow valid regions | Random generation almost never hits valid inputs. Example: a function taking a valid SQL query string. | **Table-driven tests** or **fuzz tests** with seed corpora -- offer `/generate-table-tests` or `/generate-fuzz-target` |

### BORDERLINE candidates -- ask the user before proceeding

Some functions have clear properties but require **input transformation** (sorting, deduplication, filtering to a valid subset) inside the check function before calling the target. These are borderline: property testing works but only with a workaround that changes what `testing/quick` is actually exercising.

Common patterns:
- Function requires sorted input → must call `sort.Slice` inside the check function.
- Function requires unique elements → must deduplicate inside the check function.
- Function requires a valid subset of a type (e.g., positive integers only, non-empty strings) → must filter or transform random inputs.

When the precondition is trivially satisfiable (one-line transformation), property tests can still work well. But the user should decide -- the transformation means `testing/quick` is no longer testing truly random inputs for the function's actual contract, and table-driven tests may give better coverage of boundary conditions.

If the subject is borderline, use `AskUserQuestion` with the recommended alternative as the first option and "Proceed with property tests" as the second.

## Step 3 -- Identify Properties to Test

This is the most important step. Read the function carefully and identify **universal invariants** -- statements that must be true for all valid inputs.

Look for these common property patterns:

| Property Pattern | Description | Code Shape |
|---|---|---|
| **Round-trip** | encode then decode recovers the original | `decode(encode(x)) == x` |
| **Idempotency** | applying twice equals applying once | `f(f(x)) == f(x)` |
| **Invariant preservation** | some measurable property of the output always holds | `len(f(x)) <= len(x)` |
| **Commutativity** | order of arguments does not matter | `f(a, b) == f(b, a)` |
| **Associativity** | grouping does not matter | `f(f(a, b), c) == f(a, f(b, c))` |
| **Identity element** | a special input produces no change | `f(x, identity) == x` |
| **Monotonicity** | ordering is preserved | `a <= b implies f(a) <= f(b)` |
| **Distributivity** | one operation distributes over another | `f(a, g(b, c)) == g(f(a, b), f(a, c))` |
| **No-loss / size bounds** | output is bounded relative to input | `len(output) >= len(input)` or `output <= maxVal` |
| **Oracle comparison** | result matches a simpler reference implementation | `fastImpl(x) == simpleImpl(x)` |

Present the identified properties to the user as part of the generated test file comments so they can verify the properties are actually correct.

## Step 4 -- Determine Type Generation Strategy

`testing/quick` generates random values for types that implement `quick.Generator` or have default generation. Assess each parameter type:

| Type | Default Generation | Notes |
|---|---|---|
| `bool`, `int*`, `uint*`, `float*`, `complex*` | Built-in | Works out of the box |
| `string` | Built-in | Generates random unicode strings |
| `[]T` (slices of supported types) | Built-in | Random length and contents |
| `map[K]V` (supported key/value types) | Built-in | Random size and contents |
| Structs of supported types | Built-in | Generates each field randomly |
| Pointer types `*T` | Built-in | May generate nil pointers |
| Custom types | Needs `Generate` method | Must implement `quick.Generator` interface |
| Interfaces | Not supported | Cannot generate; need concrete types |
| `chan`, `func` types | Not supported | Cannot generate |

If the function takes types that need custom generation, generate a `Generate` method:

```go
func (t MyType) Generate(rand *rand.Rand, size int) reflect.Value {
    // Build a valid MyType from random components.
    return reflect.ValueOf(MyType{
        Field: /* generate valid value using rand */,
    })
}
```

If custom generation is too complex (the type has many interrelated validity constraints), warn the user that property testing may not be the best fit.

## Step 5 -- Generate the Test File

Generate the test in the same package. Name the file `<source>_property_test.go` (e.g., `parser_property_test.go`). If the file already exists, append using the Edit tool.

Use this template structure for each property:

```go
package <pkgname>

import (
    "testing"
    "testing/quick"
)

// Property: <description of the invariant in plain English>.
func TestProperty<FunctionName>_<PropertyName>(t *testing.T) {
    t.Parallel()

    f := func(<params with supported types>) bool {
        // Arrange: construct inputs if needed.

        // Act: call the function under test.
        result := <FunctionName>(<args>)

        // Assert: verify the property holds.
        return <property assertion returning bool>
    }

    if err := quick.Check(f, nil); err != nil {
        t.Error(err)
    }
}
```

Every test function includes `t.Parallel()`. Property tests using `quick.Check` are stateless and always safe to parallelize. See [parallelism convention](../_common/references/parallelism-convention.md) for the full rule and exceptions.

Follow these generation rules:

1. **One test function per property.** Do not combine unrelated properties into a single check function. Name each test descriptively: `TestPropertyEncode_RoundTrip`, `TestPropertySort_Idempotent`, `TestPropertyNormalize_LengthBound`.

2. **Use `quick.Config` when the default iteration count is insufficient.** For functions with large input spaces, increase `MaxCount`:

```go
config := &quick.Config{MaxCount: 1000}
if err := quick.Check(f, config); err != nil {
    t.Error(err)
}
```

3. **Filter invalid inputs inside the check function.** If some random inputs are invalid for the function, return `true` (skip) rather than failing:

```go
f := func(x int) bool {
    if x == 0 {
        // Division by zero is not a valid input; skip.
        return true
    }
    return myDiv(x*2, x) == 2
}
```

But add a comment warning if the skip rate is likely to be high.

4. **Use `quick.CheckEqual` for oracle comparisons.** When comparing two implementations:

```go
func TestPropertyFastParse_MatchesSimpleParse(t *testing.T) {
    if err := quick.CheckEqual(FastParse, SimpleParse, nil); err != nil {
        t.Error(err)
    }
}
```

5. **Handle floating-point comparison** with epsilon tolerance rather than exact equality:

```go
return math.Abs(result - expected) < 1e-9
```

6. **Add custom `Generate` implementations** at the top of the file for any types that need them, before the test functions.

7. **Document each property** with a comment explaining what invariant is being tested and why it should hold. This is critical -- property tests without documented reasoning are hard to maintain.

## Step 6 -- Write the File

Write the generated test file. Before writing:

1. Check if the target file already exists.
2. If it does and contains a function with the same name, warn the user and ask whether to overwrite or rename.
3. If it exists but has no conflict, append the new test functions.
4. If the file does not exist, write a new file.

Run `gofmt` on the generated file:

```bash
gofmt -w <test_file_path>
```

## Step 7 -- Verify the Tests Pass

Run the property tests:

```bash
cd <package_directory> && go test -run "TestProperty" -count=1 -v ./... 2>&1 | tail -40
```

If tests fail:

- **Compilation error**: fix the generated code and re-run.
- **Property violation**: this means either (a) the property is wrong and needs correction, or (b) a real bug was found. Report the counterexample to the user with the failing input values so they can investigate.
- **Timeout**: the check function may be too slow for 100 iterations. Reduce `MaxCount` or simplify the property.

If a property violation reveals an actual bug, highlight this to the user -- finding bugs is the whole point.

## Step 8 -- Present Results

Report to the user:

1. The path to the generated test file.
2. A list of each property tested with its plain-English description.
3. Whether all properties passed or any counterexamples were found.
4. Any custom `Generate` implementations that were created and whether they adequately cover the input space.
5. `TODO` comments that need attention.

Remind the user:

"Property tests with `testing/quick` run 100 iterations by default. You can increase this with `quick.Config{MaxCount: N}` for higher confidence. These tests complement but do not replace example-based tests -- add table-driven tests for specific known edge cases and business logic scenarios. If you find that most random inputs are invalid for your function, consider fuzz testing with `go test -fuzz` instead, which uses coverage-guided generation to find valid inputs more efficiently."
