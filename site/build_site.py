"""Render index.html: a landing page for the game, fed by Steam.

Reads site/data/steam.json (written by site/steam.py) for the store copy, the
announcements and the artwork. Before the store page is public there is no
steam.json, so the page is rendered from site/data/prelaunch.json instead, with
artwork served from assets/ and a "coming soon" call to action.

Once live, images and the trailer thumbnail are hotlinked from Steam's CDN on
purpose: they carry a version stamp in the URL, so when the store art changes
the next fetch picks it up without any binary landing in this repository.

The page ships no script at all. Its Content-Security-Policy allows only the
one inline stylesheet (pinned by hash) and images from here and Steam's CDN.

Also renders 404.html, which GitHub Pages serves for any missing path under
this site, so its links are absolute.

Run:  python site/steam.py && python site/build_site.py
"""

import base64
import datetime
import hashlib
import html
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import landing_style as style_module

DATA = os.path.join(HERE, "data", "steam.json")
PRELAUNCH = os.path.join(HERE, "data", "prelaunch.json")
OUT = os.path.join(ROOT, "index.html")
NOT_FOUND_OUT = os.path.join(ROOT, "404.html")
LEGAL_PAGES = ["privacy-policy.html", "terms-of-service.html"]

NEWS_SHOWN = 4
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

STEAM_IMAGE_HOSTS = [
    "https://shared.akamai.steamstatic.com",
    "https://cdn.akamai.steamstatic.com",
    "https://shared.fastly.steamstatic.com",
    "https://shared.cloudflare.steamstatic.com",
]

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{name} - {tagline}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{description}">
<meta property="og:title" content="{name}">
<meta property="og:description" content="{description}">
<meta property="og:image" content="{og_image}">
<meta property="og:type" content="website">
<style>{css}</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-inner">
    <a class="topbar-brand" href="#top">&#9635; {name}</a>
    <nav class="topbar-nav" aria-label="Sections">
{nav}
    </nav>
    {topbar_cta}
  </div>
</div>

<header class="hero" id="top">
  <img class="hero-bg" src="{header_image}" alt="" role="presentation">
  <div class="wrap">
    <a class="kicker studio-link" href="{studio_url}">{developer}</a>
    <h1>{name}</h1>
    <p class="lede">{description}</p>
    <div class="hero-actions">
      {hero_cta}
      <a class="btn ghost" href="#media">See screenshots</a>
    </div>
    <div class="chips">{chips}</div>
    <a class="hero-art" href="{art_href}" aria-label="{name}">
      <img src="{header_image}" alt="{name} store artwork" width="920" height="430">
    </a>
  </div>
</header>

<main>
{news_block}
  <section class="block" id="media">
    <div class="wrap">
      <div class="block-head">
        <span class="kicker">Gallery</span>
        <h2>On the board</h2>
        <p class="block-dek">{media_dek}</p>
      </div>
      <div class="media-grid">
{media}
      </div>
    </div>
  </section>

  <section class="block" id="legal">
    <div class="wrap">
      <div class="block-head">
        <span class="kicker">Legal</span>
        <h2>The small print</h2>
        <p class="block-dek">What data the game collects, and the rules for using it.</p>
      </div>
      <div class="legal-row">
        <a class="btn ghost" href="privacy-policy.html">Privacy Policy</a>
        <a class="btn ghost" href="terms-of-service.html">Terms of Service</a>
      </div>
    </div>
  </section>
</main>

<div class="wrap">
  <footer class="site">
    <span>© {year} <a href="{studio_url}">{developer}</a> · <a href="mailto:{email}">{email}</a></span>
    <span>{updated}</span>
  </footer>
</div>

</body>
</html>
"""

NOT_FOUND = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>Page not found - {name}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<style>{css}</style>
</head>
<body>

<header class="hero">
  <div class="wrap">
    <span class="kicker">404</span>
    <h1>Nothing down here</h1>
    <p class="lede">This page does not exist. It may have moved, or the link was mistyped.</p>
    <div class="hero-actions">
      <a class="btn" href="{site_url}">Back to {name}</a>
      <a class="btn ghost" href="{studio_url}">Tiny Depth Studio</a>
    </div>
  </div>
</header>

<div class="wrap">
  <footer class="site">
    <span>© {year} <a href="{studio_url}">{developer}</a> · <a href="mailto:{email}">{email}</a></span>
  </footer>
</div>

</body>
</html>
"""

NEWS_BLOCK = """  <section class="block" id="news">
    <div class="wrap">
      <div class="block-head">
        <span class="kicker">Updates</span>
        <h2>Fresh off the grid</h2>
        <p class="block-dek">Pulled from the Steam announcements - this page rebuilds itself when a new one goes up.</p>
      </div>
      <div class="news-grid">
{news}
      </div>
      <div class="block-more"><a class="btn ghost" href="{news_hub}">All announcements on Steam</a></div>
    </div>
  </section>
"""

NEWS_CARD = """      <a class="news-card" href="{url}">
        <span class="news-meta"><span>{date}</span><span>{feedlabel}</span></span>
        <h3>{title}</h3>
        <p>{excerpt}</p>
        <span class="more">Read on Steam →</span>
      </a>"""

SHOT = """      <a class="shot{extra}" href="{href}">
        <img src="{src}" alt="{alt}" loading="lazy" width="600" height="338">
      </a>"""

EMAIL = "tinydepthstudio@gmail.com"
STUDIO_URL = "https://tiny-depth-studio.github.io/"
SITE_URL = "https://tiny-depth-studio.github.io/Clicker-Button-Legal/"


def esc(text):
    return html.escape(text or "", quote=True)


def stamp(unix_seconds):
    moment = datetime.datetime.fromtimestamp(unix_seconds, datetime.timezone.utc)
    return "{0} {1} {2}".format(moment.day, MONTHS[moment.month - 1], moment.year)


def content_security_policy(css):
    digest = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii")
    return "; ".join([
        "default-src 'none'",
        "img-src 'self' " + " ".join(STEAM_IMAGE_HOSTS),
        "style-src 'sha256-{0}'".format(digest),
        "base-uri 'none'",
        "form-action 'none'",
        "upgrade-insecure-requests",
    ])


def stamp_legal_pages():
    """Re-pin the policy hash on the hand-written legal pages.

    Their stylesheet is edited by hand, and a stale hash would silently drop all
    styling, so every build recomputes it from the page's own <style> block.
    """
    for name in LEGAL_PAGES:
        path = os.path.join(ROOT, name)
        text = io.open(path, encoding="utf-8").read()
        css = re.search(r"<style>(.*?)</style>", text, re.S).group(1)
        digest = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii")
        policy = "; ".join([
            "default-src 'none'",
            "style-src 'sha256-{0}'".format(digest),
            "base-uri 'none'",
            "form-action 'none'",
            "upgrade-insecure-requests",
        ])
        stamped, count = re.subn(
            r'(<meta http-equiv="Content-Security-Policy" content=")[^"]*(">)',
            lambda match: match.group(1) + policy + match.group(2), text, count=1)
        if count != 1:
            raise ValueError("{0} has no Content-Security-Policy meta tag".format(name))
        if stamped != text:
            io.open(path, "w", encoding="utf-8", newline="\n").write(stamped)


def load_data():
    if os.path.exists(DATA):
        data = json.load(io.open(DATA, encoding="utf-8"))
        data["app"]["store_live"] = True
        return data
    return json.load(io.open(PRELAUNCH, encoding="utf-8"))


def chips(app):
    values = []
    if not app["store_live"]:
        values.append('<span class="chip free">Coming soon to Steam</span>')
    elif app.get("is_free"):
        values.append('<span class="chip free">Free to play</span>')
    if app.get("release_date"):
        values.append('<span class="chip">Released {0}</span>'.format(esc(app["release_date"])))
    for platform in app.get("platforms", []):
        values.append('<span class="chip">{0}</span>'.format(esc(platform.title())))
    for genre in app.get("genres", [])[:4]:
        values.append('<span class="chip">{0}</span>'.format(esc(genre)))
    return "".join(values)


def calls_to_action(app):
    if app["store_live"]:
        label = "Play free on Steam" if app.get("is_free") else "Get it on Steam"
        hero = '<a class="btn" href="{0}">{1}</a>'.format(esc(app["store_url"]), label)
        topbar = '<a class="btn sm topbar-cta" href="{0}">Steam</a>'.format(esc(app["store_url"]))
    else:
        hero = '<span class="btn soon" aria-disabled="true">Coming soon to Steam</span>'
        topbar = '<span class="btn sm topbar-cta soon" aria-disabled="true">Coming soon</span>'
    return hero, topbar


def nav_links(has_news):
    links = []
    if has_news:
        links.append('      <a href="#news">Updates</a>')
    links.append('      <a href="#media">Screenshots</a>')
    links.append('      <a href="#legal">Legal</a>')
    return "\n".join(links)


def news_block(data):
    items = data.get("news") or []
    if not items:
        return ""
    cards = "\n".join(
        NEWS_CARD.format(
            url=esc(item["url"]),
            date=stamp(item["date"]),
            feedlabel=esc(item.get("feedlabel") or "Steam"),
            title=esc(item["title"]),
            excerpt=esc(item["excerpt"]),
        )
        for item in items[:NEWS_SHOWN]
    )
    return NEWS_BLOCK.format(
        news=cards,
        news_hub="https://steamcommunity.com/app/{0}/allnews/".format(data["app"]["id"]))


def media_tiles(data):
    tiles = []
    trailer = data.get("trailer")
    if trailer:
        tiles.append(SHOT.format(
            extra=" trailer",
            href=esc(data["app"]["store_url"]),
            src=esc(trailer["thumb"]),
            alt=esc("{0} trailer".format(data["app"]["name"])),
        ))
    for index, shot in enumerate(data.get("screenshots", []), start=1):
        tiles.append(SHOT.format(
            extra="",
            href=esc(shot["full"]),
            src=esc(shot["thumb"]),
            alt=esc("{0} screenshot {1}".format(data["app"]["name"], index)),
        ))
    return "\n".join(tiles)


def absolute(url):
    return url if url.startswith("https://") else SITE_URL + url


def main():
    data = load_data()
    app = data["app"]
    news = data.get("news") or []
    newest = max((item["date"] for item in news), default=None)
    shots = len(data.get("screenshots", []))
    media_dek = "{0} shots from the board{1}.".format(
        shots, ", plus the trailer" if data.get("trailer") else "")
    hero_cta, topbar_cta = calls_to_action(app)
    css = style_module.CSS

    page = PAGE.format(
        csp=content_security_policy(css),
        css=css,
        name=esc(app["name"]),
        tagline="Shape-fitting 3D clicker game",
        description=esc(app["short_description"]),
        header_image=esc(app["header_image"]),
        og_image=esc(absolute(app["header_image"])),
        art_href=esc(app["store_url"] if app["store_live"] else "#media"),
        nav=nav_links(bool(news)),
        topbar_cta=topbar_cta,
        hero_cta=hero_cta,
        developer=esc((app.get("developers") or ["Tiny Depth Studio"])[0]),
        chips=chips(app),
        news_block=news_block(data),
        media=media_tiles(data),
        media_dek=esc(media_dek),
        year=datetime.datetime.fromtimestamp(newest, datetime.timezone.utc).year if newest else 2026,
        updated="Updated " + stamp(newest) if newest else "",
        email=EMAIL,
        studio_url=STUDIO_URL,
    )
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(page)
    not_found = NOT_FOUND.format(
        csp=content_security_policy(css),
        css=css,
        name=esc(app["name"]),
        site_url=SITE_URL,
        developer=esc((app.get("developers") or ["Tiny Depth Studio"])[0]),
        year=datetime.datetime.fromtimestamp(newest, datetime.timezone.utc).year if newest else 2026,
        email=EMAIL,
        studio_url=STUDIO_URL,
    )
    io.open(NOT_FOUND_OUT, "w", encoding="utf-8", newline="\n").write(not_found)
    stamp_legal_pages()
    print("index.html ({0}): {1} news, {2} media tiles".format(
        "store" if app["store_live"] else "pre-launch",
        min(NEWS_SHOWN, len(news)), shots + (1 if data.get("trailer") else 0)))


if __name__ == "__main__":
    main()
