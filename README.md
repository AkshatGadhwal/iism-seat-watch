# IISM seat watch

Checks the IISM Gulmarg admission form every 5 minutes (GitHub Actions) and alerts when a
Basic SSC schedule has seats: WhatsApp (CallMeBot), phone push (ntfy) and a GitHub
"failed run" email. Read-only: it never submits the form.

- Change course / level / state in `.github/workflows/check.yml`.
- Stop it: Actions tab -> "IISM seat check" -> "..." -> Disable workflow.
