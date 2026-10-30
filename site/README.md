# Landing page build

`index.html` in the repository root is **generated**. Edit the files here and rebuild;
never hand-edit the HTML, the next build overwrites it.

```bash
python site/steam.py        # fetch store data + announcements -> site/data/steam.json
python site/build_site.py   # render index.html, re-pin the legal pages' CSP hash
```

Same layout as `Clicker-Ore-Legal`, so a fix in one carries over to the other.

## What lives where

| File | Holds |
| --- | --- |
| `steam.py` | the only place that talks to Steam. Writes `data/steam.json` once the store page is public. |
| `data/steam.json` | **generated, committed.** Store copy, artwork URLs, the six newest announcements. Absent until launch. |
| `data/prelaunch.json` | hand-written stand-in used while `steam.json` does not exist: store short description, local artwork under `assets/`, "coming soon" call to action. |
| `build_site.py` | renders `index.html` and `404.html` (served by Pages for any missing path) and refreshes the Content-Security-Policy hash in `privacy-policy.html` and `terms-of-service.html`. |
| `landing_style.py` | the landing page stylesheet (Clicker Ore's, recoloured to the Clicker Button sky blue and button gold). |

## Before and after launch

Steam's `appdetails` answers `success: false` until the store page is public. `steam.py`
then writes nothing and the page renders from `prelaunch.json`. The first scheduled run
after the page goes public writes `steam.json`, and the landing page switches to the
store data, the Steam call to action and the announcements on its own. After that,
`assets/store` and `assets/screenshots` are no longer referenced and can be deleted.

## Security

The pages ship no JavaScript. Each one carries a Content-Security-Policy `<meta>` that
allows only its own inline stylesheet (pinned by SHA-256 hash), images from this site
and Steam's CDN, and nothing else (`default-src 'none'`, no forms, no `<base>`).
Editing a stylesheet by hand is fine: `build_site.py` recomputes the hash on every
build, and the workflow runs on every push that touches the pages.

## How it stays current

`.github/workflows/steam-refresh.yml` runs twice a day (05:23 and 17:23 UTC), on every
push that touches `site/` or the legal pages, and on demand from the Actions tab. It
commits only when something actually changed. Actions are pinned to commit SHAs;
Dependabot (`.github/dependabot.yml`) proposes updates monthly.

- The app id lives in `steam.py` (`APP_ID = 5526030`).
