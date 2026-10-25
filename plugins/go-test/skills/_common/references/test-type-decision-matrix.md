# Test Type Decision Matrix

Use this matrix to determine which Go test type best fits the code under test. Each generation skill links here so users can see the full picture.

## Decision Matrix

Rows are code characteristics; columns are test types. Ratings: **best** = strongly recommended, **good** = solid fit, **maybe** = works but another type is better, **bad** = wrong tool, `-` = not applicable.

| Characteristic | Table | Benchmark | Fuzz | Property | txtar | Mocks | Adversarial |
|---|---|---|---|---|---|---|---|
| Pure function, discrete inputs | **best** | - | maybe | maybe | bad | - | maybe |
| Encode/decode pair, round-trip | maybe | - | good | **best** | bad | - | maybe |
| Parse/validate untrusted input | maybe | - | **best** | maybe | bad | - | good |
| CLI tool / file-based workflow | bad | - | bad | bad | **best** | - | bad |
| Performance-sensitive hot path | - | **best** | - | - | bad | - | - |
| Code depending on interfaces | good | - | - | - | - | **best** | good |
| Sort/idempotent/algebraic | maybe | - | maybe | **best** | bad | - | maybe |
| Stateful / side-effecting | good | - | bad | bad | maybe | good | **best** |
| HTTP handler | good | maybe | - | - | bad | good | good |

## Per-Test-Type Summary

- **Table tests** (`/generate-table-tests`): Verify specific input/output pairs using subtests. Best for pure functions with discrete, enumerable inputs and known edge cases.
- **Benchmarks** (`/generate-benchmark`): Measure ns/op, allocations, and throughput. Best for performance-sensitive code where you need to compare before/after or track regressions.
- **Fuzz targets** (`/generate-fuzz-target`): Automatically explore the input space to find crashes and panics. Best for parsers, validators, and deserializers that handle untrusted input.
- **Property tests** (`/generate-property-tests`): Verify universal invariants (round-trip, idempotency, algebraic laws) across randomly generated inputs. Best for encode/decode pairs and pure transformations with provable properties.
- **txtar script tests** (`/generate-txtar-tests`): Test CLI tools and file-based workflows by declaring files, running commands, and checking output. Best for anything invoked as a command.
- **Mocks** (`/generate-mocks`): Isolate code from its dependencies by replacing interfaces with test doubles. Best when the code under test depends on interfaces you don't want to invoke in tests.
- **Adversarial tests** (`/generate-adversarial-tests`): Deliberately probe a function's assumptions, boundary conditions, and undocumented behaviors. Best for stateful code, complex APIs with preconditions, and functions handling interfaces.

## Redirect Phrasing Template

All skills use this pattern when redirecting to a better-fitting test type:

> "[Current test type] tests verify [what they verify]. For [this code's characteristics], [alternative](/generate-alternative) is a better fit because [reason]. Would you like to switch?"

Use `AskUserQuestion` for borderline cases, with the recommended alternative as the first option and "Proceed with [current type]" as the second.
