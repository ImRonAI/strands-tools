# Verification Guidelines

Work in the assigned tests directory; inherit root and package guidance. Use native framework clients/model fixtures and HTTP-level contract fixtures, not invented substitute engines. Actual commands come from the package manifest; an empty test folder does not establish a working suite.

Read `docs/reference/fastmcp/pages/testing.md`, selected Client/task/interactivity docs, and VERIFIED_DECISIONS. Distinguish source presence, SDK-fixture execution, real HTTP/browser behavior, controlled live delivery and load tests. Never report one category as proof of another.

Required failure coverage includes wrong user/audience/expired credentials, denied/disabled operation, malformed input, serialization/media failure, ambiguous mutation timeout, task cancellation/restart and UI host policy denial. Keep raw result/resource MIME/CSP/metadata in contracts. Native mock models prove tool loop mechanics, not model quality.

Do not execute purchases/messages/calls/domain mutations/destructive actions with live credentials unless the user has explicitly authorized controlled targets. No blanket transient retry that duplicates side effects. Evidence is redacted; every spawned fixture process/port/browser/store has task-owned teardown. Confirm the default model listing remains at most four even with app-only backends; visibility alone does not prove authorization.

## Assigned directory
Project target: `packages/app/tests/contracts`. Change into this directory before development. This copy is a planning template; the project scaffold is not installed until the worker applies it.
