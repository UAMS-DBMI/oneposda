# Activity Based Curation (web/abc)

React + TypeScript replacement for the Perl `ActivityBasedCuration` GUI. It is
a static bundle served by nginx at `/abc/` and talks to the Posda API at
`/papi/v1/abc`, authenticating with the same `logintoken` cookie the rest of
Posda uses. The plan is in `notes/abc-gui-replacement-plan.md`.

```sh
bun install
bun run dev        # http://localhost:5173/abc/ ; /papi is proxied to the compose nginx on :80
bun run test       # vitest
bun run typecheck  # tsc -b
bun run build      # dist/ (copied to /www/abc by web/Dockerfile)
```

Sign in with a Posda account that has the `launch` permission on the
`ActivityBasedCuration` app.
