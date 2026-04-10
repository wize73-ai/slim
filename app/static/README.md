# `app/static/` — CSS, JS, images

**Student-editable.** Your styling and static assets go here, served at `/static/`.

## v1 state

Empty. The dumb v1 chat UI uses no CSS beyond the browser default. Making it
look decent is an early PR opportunity.

## A note on dependencies

Client-side JS libraries (anything you'd normally `npm install`) can be
vendored here as static files. No build step, no `package.json`. Keep it
simple — HTMX plus a little hand-written JS will carry you far.

If you find yourself wanting a full JS framework, stop and ask whether
the feature genuinely needs one. The answer is usually no.
