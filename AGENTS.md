# AGENTS.md — strands-tools (Agent Factory MCP, used by the Branding-App Venture Journey project)

## 0. Hard Rule for Every Coding Agent (non-negotiable, overrides everything below)

Before writing any code for an issue, and again before marking it done:

1. **Review the issue first.** Read the whole issue, its PRD, and every file it names.
2. **Validate every statement.** Check every type, prop, function signature, config field, endpoint, model id, package version, and `file:line` reference in the issue against its real source:
   - the installed package's `.d.ts`/source in `node_modules` (or the Python `site-packages`);
   - the official documentation page of that library, SDK, or API;
   - a real call against the real service.

   Record the source next to each confirmed item in the issue. If something cannot be confirmed, stop and ask the founder. Never guess, never work around it.
3. **Prove it is the simplest solution.** Confirm the planned change is the most straightforward way to deliver exactly what the issue asks. Prefer adjusting existing working code over replacing it. Change as few files and lines as possible. If the issue itself asks for something more complex than needed, stop and propose the simpler version to the founder before coding.
4. **Native implementations only.** Use each library, SDK, and API exactly as its official documentation shows. No wrappers, patches, monkey-patching, subclassing to change behavior, re-implemented clients, or custom loops around them. Never stray from the native implementation.
5. **Only requested custom code.** Write custom code only where the founder or the issue explicitly asks for it, and only to the extent asked. No extra features, abstractions, helpers, fallbacks, or "just in case" code.
6. **Strictest type checking.** All code changes must pass TypeScript with the strictest settings (`strict: true`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noPropertyAccessFromIndexSignature`, `noFallthroughCasesInSwitch`, `noUnusedLocals`, `noUnusedParameters`). No `any`, no `as any`, no `@ts-ignore`/`@ts-expect-error`, and no non-null `!` assertions unless the library's own docs show them. Python code must pass `pyright --strict`.
7. **Report.** In the issue, list what you verified (with sources), what you changed (files and why), and anything you stopped on.
8. **Strict checking must be switched on, not just promised.** Before your first code change, confirm `tsconfig.json` contains every flag in rule 6, and that `pyright` runs in `strict` mode in Python packages. If any flag is missing, stop and ask the founder how to handle existing errors in untouched files, then add the flags. Run `npm run lint` (`tsc --noEmit`) and, for Python, `pyright` before marking any issue done.
9. **No unverified issues get coded.** If an issue contains `UNVERIFIED`, "verify during implementation", "decide during implementation", or any claim without a source, stop. Resolve each item against its official source, or ask the founder, before writing code. Never resolve it by guessing.
10. **Only founder requests and library requirements count as "requested".** Anything in an issue that can't be traced to a founder decision (the PRD's "Founder decisions" section, or an explicit founder message) or to a requirement of the library, SDK, or API involved, counts as unrequested. Ask the founder before building it. This includes designs, UI details, wording, defaults, limits, and notifications written into issues by earlier agents.
11. **Rules apply in every repo touched.** Work in another repository for this project (for example `~/Desktop/strands-tools`) follows this same Section 0. Check that repo's `AGENTS.md` carries it; if not, stop and tell the founder.

Breaking any part of this rule means the work is rejected.

