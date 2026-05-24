#!/usr/bin/env python3
"""
Build script for Michael Harmon's site.

Reads content from page folders (writing/, about/, contact/) and generates
a static HTML site into _site/.

Run from repo root:  python3 _build/build.py
"""

import json
import os
import re
import shutil
from html import escape
from pathlib import Path

import yaml

# ─── Paths ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "_build"
SITE = ROOT / "_site"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"}


# ─── Markdown → HTML ─────────────────────────────────────────────────────────

def md_inline(text: str) -> str:
    """Convert inline markdown (links, bold, italic) to HTML. Escapes first."""
    text = escape(text)

    def link_repl(m):
        label, url = m.group(1), m.group(2)
        if url.startswith(("/", "#", "mailto:")):
            return f'<a href="{url}">{label}</a>'
        return f'<a href="{url}" target="_blank" rel="noopener">{label}</a>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # &rarr; etc. were escaped by html.escape above; un-escape the &amp; back to &
    # so HTML entities written in markdown render as glyphs.
    text = text.replace("&amp;rarr;", "&rarr;").replace("&amp;larr;", "&larr;")
    text = text.replace("&amp;mdash;", "&mdash;").replace("&amp;ndash;", "&ndash;")
    text = text.replace("&amp;hellip;", "&hellip;").replace("&amp;amp;", "&amp;")
    return text


def md_to_html(md: str) -> str:
    """Convert a block of markdown to HTML paragraphs."""
    paras = [p.strip() for p in md.strip().split("\n\n") if p.strip()]
    return "\n".join(f"<p>{md_inline(p)}</p>" for p in paras)


# ─── Image discovery ─────────────────────────────────────────────────────────

def scan_images(page_dir: Path) -> list[str]:
    img_dir = page_dir / "images"
    if not img_dir.is_dir():
        return []
    return sorted(
        f.name for f in img_dir.iterdir() if f.suffix.lower() in IMAGE_EXTS
    )


def copy_page_images(slug: str) -> None:
    src = ROOT / slug / "images"
    if not src.is_dir():
        return
    dest = SITE / "images" / slug
    dest.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.suffix.lower() in IMAGE_EXTS:
            shutil.copy2(f, dest / f.name)


# ─── HTML layout ─────────────────────────────────────────────────────────────

GOOGLE_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" '
    'href="https://fonts.googleapis.com/css2?'
    'family=Lora:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&'
    'family=Libre+Franklin:wght@300;400;500;600;700&'
    'display=swap">'
)


def render_nav(config: dict, current_path: str) -> str:
    items = []
    for item in config["nav"]:
        cls = ' class="active"' if item["path"] == current_path else ""
        items.append(f'<a href="{item["path"]}"{cls}>{escape(item["label"])}</a>')
    return "\n      ".join(items)


def render_seo_head(config: dict, *, full_title: str, current_path: str) -> str:
    """
    Build the invisible-to-visitors <head> SEO block: meta description,
    canonical, Open Graph / Twitter Card, and schema.org Person JSON-LD.
    Degrades to an empty string if config['seo'] is absent.
    """
    seo = config.get("seo") or {}
    base_url = (seo.get("base_url") or "").rstrip("/")
    description = seo.get("description") or ""
    og_image = seo.get("og_image") or ""
    same_as = seo.get("same_as") or []
    gsv = seo.get("google_site_verification") or ""

    if not (base_url or description):
        return ""

    canonical = f"{base_url}{current_path}" if base_url else ""
    if canonical and not canonical.endswith("/"):
        canonical += "/"

    if og_image and og_image.startswith("/") and base_url:
        og_image = base_url + og_image

    lines: list[str] = []
    if gsv:
        lines.append(f'<meta name="google-site-verification" content="{escape(gsv)}">')
    if description:
        lines.append(f'<meta name="description" content="{escape(description)}">')
    if canonical:
        lines.append(f'<link rel="canonical" href="{escape(canonical)}">')

    # Open Graph / Twitter
    lines.append('<meta property="og:type" content="website">')
    lines.append(f'<meta property="og:title" content="{full_title}">')
    if description:
        lines.append(f'<meta property="og:description" content="{escape(description)}">')
    if canonical:
        lines.append(f'<meta property="og:url" content="{escape(canonical)}">')
    if og_image:
        lines.append(f'<meta property="og:image" content="{escape(og_image)}">')
    lines.append('<meta name="twitter:card" content="summary_large_image">')

    # schema.org Person — helps Google disambiguate which Michael Harmon this is.
    # We don't assert worksFor (he's a contributor, not staff); the sameAs link
    # to his NYT author page is the signal that ties him to the Times.
    person = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": config["site_name"],
        "url": base_url + "/" if base_url else None,
        "jobTitle": seo.get("job_title"),
        "sameAs": same_as or None,
    }
    person = {k: v for k, v in person.items() if v is not None}
    lines.append(
        '<script type="application/ld+json">'
        + json.dumps(person, ensure_ascii=False)
        + "</script>"
    )

    return "\n  " + "\n  ".join(lines)


def render_page(config: dict, *, title: str, current_path: str, body: str) -> str:
    site_name = escape(config["site_name"])
    seo = config.get("seo") or {}
    home_title = escape(seo.get("title") or config["site_name"])
    full_title = home_title if current_path == "/" else f"{escape(title)} | {site_name}"
    nav = render_nav(config, current_path)
    seo_head = render_seo_head(config, full_title=full_title, current_path=current_path)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{full_title}</title>{seo_head}
  {GOOGLE_FONTS}
  <link rel="stylesheet" href="/style.css">
</head>
<body id="top">
  <header>
    <div class="header-inner">
      <a class="site-name" href="/">{site_name}</a>
      <button class="menu-toggle" aria-label="Open menu" aria-expanded="false">
        <span></span><span></span><span></span>
      </button>
      <nav>
        <button class="nav-close" aria-label="Close menu">&times;</button>
        {nav}
      </nav>
    </div>
    <div class="nav-backdrop"></div>
  </header>

  <div class="page-content">
    <main>
{body}
    </main>

    <footer>
      <a class="back-to-top" href="#top">Back to top <span>&#8963;</span></a>
      <p class="copyright">{escape(config.get("copyright", ""))}</p>
    </footer>
  </div>

  <script>
    document.querySelectorAll('nav a').forEach(function(a) {{
      a.addEventListener('click', function(e) {{
        if (a.pathname === location.pathname) return;
        e.preventDefault();
        document.querySelector('.page-content').classList.add('leaving');
        setTimeout(function() {{ location.href = a.href; }}, 250);
      }});
    }});
    window.addEventListener('pageshow', function(e) {{
      if (e.persisted) document.querySelector('.page-content').classList.remove('leaving');
    }});
    var hdr = document.querySelector('header');
    window.addEventListener('scroll', function() {{
      hdr.classList.toggle('hidden', window.scrollY > 400);
    }}, {{ passive: true }});
    var io = new IntersectionObserver(function(entries) {{
      entries.forEach(function(e) {{
        if (e.isIntersecting) {{
          e.target.style.opacity = 1;
          io.unobserve(e.target);
        }}
      }});
    }}, {{ threshold: 0.05 }});
    document.querySelectorAll('.scroll-fade').forEach(function(el) {{
      el.style.opacity = 0;
      io.observe(el);
    }});
    var mt = document.querySelector('.menu-toggle');
    var nc = document.querySelector('.nav-close');
    var nb = document.querySelector('.nav-backdrop');
    function setNav(open) {{
      document.body.classList.toggle('nav-open', open);
      mt.setAttribute('aria-expanded', open);
    }}
    mt.addEventListener('click', function() {{ setNav(true); }});
    nc.addEventListener('click', function() {{ setNav(false); }});
    nb.addEventListener('click', function() {{ setNav(false); }});
  </script>
</body>
</html>
"""


def write_page(path: str, html: str) -> None:
    if path == "/":
        out = SITE / "index.html"
    else:
        out = SITE / path.strip("/") / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"  wrote {out.relative_to(SITE)}")


def write_robots_and_sitemap(config: dict) -> None:
    """Emit robots.txt and sitemap.xml into _site/ from config['nav']."""
    seo = config.get("seo") or {}
    base_url = (seo.get("base_url") or "").rstrip("/")
    if not base_url:
        return

    sitemap_url = f"{base_url}/sitemap.xml"
    (SITE / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n",
        encoding="utf-8",
    )

    urls = []
    for item in config["nav"]:
        path = item["path"]
        loc = base_url + (path if path.endswith("/") else path + "/")
        urls.append(f"  <url><loc>{escape(loc)}</loc></url>")
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )
    (SITE / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    print("  wrote robots.txt")
    print("  wrote sitemap.xml")


# ─── Page builders ───────────────────────────────────────────────────────────

def build_writing(config: dict) -> None:
    """The Writing page is the homepage. Big nameplate + list of pieces."""
    intro = (ROOT / "writing" / "text.md").read_text(encoding="utf-8")
    items_path = ROOT / "writing" / "writing.yml"
    items = yaml.safe_load(items_path.read_text(encoding="utf-8")) or []

    heading = escape(config.get("home_heading", config["site_name"]))
    tagline = escape(config.get("tagline", ""))
    tagline_html = f'<p class="nameplate-tagline">{tagline}</p>' if tagline else ""

    nameplate = f"""    <section class="nameplate">
      <h1 class="nameplate-name">{heading}</h1>
      {tagline_html}
    </section>"""

    def item_html(s: dict, *, featured: bool = False) -> str:
        kicker = escape(s.get("kicker", "")) if s.get("kicker") else ""
        title = escape(s["title"])
        dek = escape(s.get("dek", ""))
        publication = escape(s.get("publication", ""))
        date = escape(s.get("date", ""))
        link = escape(s["link"])

        byline_parts = []
        if publication:
            byline_parts.append(f'<span class="story-pub">{publication}</span>')
        if date:
            byline_parts.append(f'<span class="story-date">{date}</span>')
        byline = " · ".join(byline_parts)

        kicker_html = f'<p class="story-kicker">{kicker}</p>' if kicker else ""

        image = s.get("image")
        focus = s.get("focus")
        image_html = ""
        if image:
            style_attr = f' style="object-position: {escape(str(focus))}"' if focus else ""
            image_html = (
                f'<a class="story-image" href="{link}" target="_blank" rel="noopener">'
                f'<img src="/images/writing/{escape(image)}" alt="" loading="lazy"{style_attr}>'
                f'</a>'
            )

        cls = "story story-featured" if featured else "story"
        return f"""      <article class="{cls}">
        {image_html}
        <div class="story-text">
          {kicker_html}
          <h2 class="story-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></h2>
          <p class="story-dek">{dek}</p>
          <p class="story-byline">{byline}</p>
        </div>
      </article>"""

    if not items:
        list_html = '<p class="stories-empty">More coming soon.</p>'
    else:
        featured = next((s for s in items if s.get("featured")), None)
        rest = [s for s in items if s is not featured]
        parts = []
        if featured:
            parts.append(item_html(featured, featured=True))
        if rest:
            cards = "\n".join(item_html(s) for s in rest)
            parts.append(f'      <div class="story-grid">\n{cards}\n      </div>')
        list_html = "\n".join(parts)

    intro_html = md_to_html(intro)
    body = f"""{nameplate}

    <section class="writing-intro">
      <div class="page-intro">
{intro_html}
      </div>
    </section>

    <section class="stories">
{list_html}
    </section>"""

    write_page("/", render_page(config, title=config["site_name"], current_path="/", body=body))
    copy_page_images("writing")


def build_about(config: dict) -> None:
    text = (ROOT / "about" / "text.md").read_text(encoding="utf-8")
    images = scan_images(ROOT / "about")
    portrait = next((f for f in images if f.lower().startswith("portrait")), None)

    portrait_html = ""
    if portrait:
        portrait_html = (
            f'        <div class="portrait">'
            f'<img src="/images/about/{portrait}" alt="Portrait of {escape(config["site_name"])}">'
            f'</div>'
        )

    body = f"""    <section class="about-band">
      <div class="about-inner">
{portrait_html}
        <div class="bio-text">
{md_to_html(text)}
        </div>
      </div>
    </section>"""

    write_page("/about", render_page(config, title="About", current_path="/about", body=body))
    copy_page_images("about")


def build_contact(config: dict) -> None:
    text = (ROOT / "contact" / "text.md").read_text(encoding="utf-8")
    form_name = escape(config.get("contact_form_name", "contact"))

    form_html = f"""      <form class="contact-form" name="{form_name}" method="POST" netlify netlify-honeypot="bot-field" action="/contact/?sent=1">
        <input type="hidden" name="form-name" value="{form_name}">
        <input type="hidden" name="bot-field" class="hp" tabindex="-1" autocomplete="off">

        <label class="field">
          <span class="field-label">Name</span>
          <input type="text" name="name" required autocomplete="name">
        </label>

        <label class="field">
          <span class="field-label">Email</span>
          <input type="email" name="email" required autocomplete="email">
        </label>

        <label class="field">
          <span class="field-label">Message</span>
          <textarea name="message" rows="6" required></textarea>
        </label>

        <button type="submit" class="contact-submit">Send</button>
      </form>"""

    body = f"""    <section class="page-head">
      <h1 class="page-title">Contact</h1>
    </section>

    <section class="contact-simple">
      <div class="contact-intro">
{md_to_html(text)}
      </div>

      <div class="contact-thanks" hidden>
        <p>Thanks — your message is on its way. I'll be in touch.</p>
      </div>

{form_html}
    </section>

    <script>
    (function() {{
      var params = new URLSearchParams(location.search);
      if (params.get('sent') === '1') {{
        var form = document.querySelector('.contact-form');
        var thanks = document.querySelector('.contact-thanks');
        if (form) form.hidden = true;
        if (thanks) thanks.hidden = false;
      }}
    }})();
    </script>"""

    write_page("/contact", render_page(config, title="Contact", current_path="/contact", body=body))


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    os.chdir(ROOT)

    config = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    shutil.copy2(BUILD / "style.css", SITE / "style.css")

    print("Building pages:")
    build_writing(config)
    build_about(config)
    build_contact(config)
    write_robots_and_sitemap(config)

    print(f"\nDone. Site built to {SITE}")


if __name__ == "__main__":
    main()
