# Target Function Identification

Standard procedure for identifying the Go function to target. Each skill that references this document should substitute its own values for `<skill-purpose>` and `<candidate-guidance>`.

## Procedure

Check whether the user specified a function name and file path in their prompt.

- If the user provided both a function name and a file path, read that file and locate the function.
- If the user provided only a function name, search for it:

```bash
grep -rn "^func .*FunctionName" --include="*.go" .
```

- If the user provided only a file path, read the file and list functions that are good candidates for `<skill-purpose>` (`<candidate-guidance>`), then ask the user which function to target.
- If the user provided neither, ask: "Which function should I generate `<skill-purpose>` for? Please provide the function name and optionally the file path."

## Notes

- This procedure applies to skills that target **Go functions**. Skills targeting interfaces (generate-mocks), CLI commands (generate-txtar-tests), or package scope (find-coverage-gaps) use their own identification logic.
- If the search returns multiple matches, present them to the user and ask which one to target.
- If the search returns no matches, broaden the search by removing the `^func` anchor and searching for the name as a method receiver pattern: `grep -rn "func (.*) FunctionName" --include="*.go" .`
