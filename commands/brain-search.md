# brain-search

Search the graph across all tables for a term. Use instead of grep.

Term: `$ARGUMENTS`

## Steps

Call ALL of these in parallel for `$ARGUMENTS`:
1. `find_handler("$ARGUMENTS")` — is it an API endpoint?
2. `find_component("$ARGUMENTS")` — is it a component, hook, or TypeScript type?
3. `what_uses("$ARGUMENTS")` — where is this symbol used?
4. `get_decisions("$ARGUMENTS")` — any architectural decisions on this topic?
5. `recall("$ARGUMENTS")` — any stored facts (addresses, ports, flags)?
6. `get_history(10, "$ARGUMENTS")` — past spec implementations related to this term?

Then aggregate all non-empty results into one output:

```
🔍 Search: <term>

[API Endpoint]
  POST /api/auth/login → handlers/auth.go:42  AuthHandler.Login

[Component / Type]
  Component: LoginPage — src/pages/LoginPage.tsx
  Hooks: useAuth, useWebAuthn

[Used by]
  Components: Dashboard, AdminLayout

[Decisions]
  auth — use JWT not sessions: stateless for k8s

[Memory]
  auth_secret — loaded from GCP Secret Manager

[History]
  AUTH-01 (done) — WebAuthn + dev-login, JWT role claim
```

Skip categories where all results are empty. End with a one-line summary of what was found.
