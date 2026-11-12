# IISM seat watch

Checks the IISM Gulmarg admission form every 5 minutes (GitHub Actions) and alerts when a
Basic SSC schedule has seats: WhatsApp (CallMeBot), phone push (ntfy) and a GitHub
"failed run" email. Read-only: it never submits the form.

Each run checks every 5 minutes for ~5.5 hours, then starts the next run itself.

- Change course / level / state in `.github/workflows/check.yml`.
- Test the alerts: Actions -> "IISM seat check" -> Run workflow -> tick "Test".
- Stop it: Actions -> "IISM seat check" -> "..." -> **Disable workflow**, then open the
  running run and click **Cancel workflow**.
