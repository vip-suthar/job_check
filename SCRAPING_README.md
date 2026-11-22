# Checking a posting from a link (web scraping notes)

These notes cover the "check a posting from a link" feature: what it does, what was wrong with the first version, what we changed and why, and the things worth knowing when presenting it.

Code: `app/fetch.py` (fetching and reading pages), `app/routes.py` (`/check-url`), `app/templates/listing.html`, tests in `tests/test_fetch.py`.

## Why scraping is useful for JobCheck

- **People find job offers as links, not text.** Most fake job offers reach students as a forwarded link on WhatsApp or Telegram, or as a posting on a job board. Copying the full text out of a page, on a phone, is slow and people usually copy only part of it (just the title and salary, say). With a link, JobCheck reads the whole posting, including the parts people skip, like the company name and the "how to apply" section, which is often where the fee or the WhatsApp number is.
- **One link can hold many postings.** A suspicious "work from home jobs" page or a search results page can list 20 jobs. Opening each one and pasting it is not something anyone will do. Now the app opens them and shows which ones have red flags.
- **Same detector for every input.** Text from a link goes through the same rules and ML model as pasted text, the API and the bulk upload, so results can be compared.
- **Data collection.** The project also uses scraping offline (`scrape_pages.py`, `scrapers/scrape_carrers.py`) to collect genuine postings from official career pages for our Indian test set. Same idea, but there the output goes into a CSV for manual labelling, not straight into the detector.

## How it worked before

The first version (`fetch_text()` in `app/fetch.py`) downloaded the page safely (only public addresses, every redirect checked), then called `page_text()` from `scrape_pages.py`, which removed `script`, `style`, `nav`, `header`, `footer` tags and joined *all* remaining text into one line. That text, cut to 10,000 characters, was checked as one posting.

Problems with that:

1. **Listing pages were never opened.** If you gave it a page with many postings, it did *not* open them. It took whatever text was visible on the listing page (titles, locations, filter menus) and checked all of it as one "posting".
   - The red flags of one posting were reported for the whole page, and you could not tell which posting they came from.
   - On a big listing, only the first 10,000 characters were checked, so postings further down were never looked at.
   - Listing pages usually show only titles, so the descriptions (where scams actually show up: fees, WhatsApp numbers, "no interview") were never seen at all.
2. **It threw away the best copy of the posting.** Most job sites put the posting in the page as `<script type="application/ld+json">` with schema.org `JobPosting` data (title, company, full description). They do this so Google can show it in Google Jobs. Since every `<script>` tag was deleted first, this data was always thrown away. It is often there even when the visible page is built with JavaScript.
3. **Lots of junk text.** Application forms ("First name*, Email*, Upload resume"), sidebars, "similar jobs" boxes and button labels were all counted as part of the posting. On a Greenhouse posting this pushed the page over 10,000 characters, so the end of the real description was cut off without telling the user.
4. **No line breaks.** Everything was joined into one line, so the result page showed one huge paragraph and the highlighted phrases were hard to find.
5. **One error message for everything.** A blocked request (403), a deleted posting (404), a timeout and a PDF link all showed the same "Could not read a posting from that link" message.
6. **The link was not saved.** The result and history pages only had the text, not where it came from.
7. **Small one:** errors while reading the body of the response (a dropped connection, broken gzip) were not caught, so they would have shown a 500 error page.

## What changed

### 1. Listing pages: each posting is opened and checked separately

`posting_links()` decides if a page is a list of postings, and collects the posting links from three places:

- JSON-LD `ItemList` data (Internshala's listing pages have this, with a link and title for every internship),
- several JSON-LD `JobPosting` entries with a `url`,
- normal `<a>` links on the page, except the ones in `nav`, `header` and `footer` (menus link to categories, not postings).

A link counts as a posting link (`looks_like_posting()`) if it is on the same host name as the page and:

- the path has a job word in it, like `/jobs/12345` or `/internship/detail/...`, or it is under the listing page's own path, like `/palantir` → `/palantir/ac978161-...` (Lever does this), and
- the last part of the path has a number in it. Posting links almost always end in an id, while category links like `/jobs/python-jobs/` don't. Short numbers like `/page/2` are left out, they are pagination.

If there are at least 3 such links, the page is treated as a listing. If the page has exactly one `JobPosting` in its JSON-LD it is always treated as a single posting, even if it has a "similar jobs" box.

For a listing:

- the first **10** postings are opened, **one after the other** (like a person clicking through them), which takes about 1 to 6 seconds on the sites we tried,
- every link goes through the same safety check as the first one (public address only, each redirect checked),
- **robots.txt is checked** (`get_robots()`) before the app opens links on its own, the same way our data scraper does. A missing robots.txt (any 4xx) means everything is allowed, a server error means we stay away. This is what RFC 9309 says to do,
- each posting is saved as its own check (with its own link), so it also shows up in history, the dashboard and the monthly report,
- the results page (`listing.html`) lists every posting with its title, link and result. Postings that were not opened (past the first 10, blocked by robots.txt, or failed) say why and have a "Check this one" button,
- a "Check the page text as one posting" button is there in case a single posting is mistaken for a listing.

We don't check robots.txt for the page the user typed in. That is the user asking to see one page, like opening it in a browser. robots.txt is meant for automated crawling, which is what opening the links on our own is.

### 2. Better text from each posting

`posting_text()`:

1. Uses the JSON-LD `JobPosting` data if the page has it (title, company, description). If that description is very short, it also reads the page and keeps whichever is longer.
2. Otherwise reads `<main>` or `<article>` (or the whole body if neither has real text) and removes `script`, `style`, `nav`, `footer`, `aside`, `form`, `button`, `iframe` and similar. `header` is only removed when reading the whole body, because inside `<main>` a header is usually the job title.

`html_to_text()` keeps a line break after block tags (`p`, `li`, `h2`, `div`...) but not inline tags (`b`, `a`, `span`). That matters for detection: the negation check in `detector/rules.py` looks only at the same sentence and treats a newline as the end of one. If `We <b>never</b> charge a <a>registration fee</a>` were split on every tag, "never" would end up on a different line and the fee rule would wrongly fire. There is a test for this case.

### 3. Clearer error messages

`download()` turns every failure into a message the user can act on, for example:

- "the site blocked automated access (HTTP 403)"
- "the page was not found (HTTP 404), the posting may have been removed"
- "the site took too long to respond"
- "the link is not a web page" (PDFs, images)
- "the page has almost no text, it may need JavaScript or a login to show the posting"

The message always ends with "Please copy the posting text and paste it below", so the user knows what to do next.

### 4. Other improvements

- If the posting is longer than 10,000 characters, the user is told only the first 10,000 were checked (before, it was cut silently).
- The link is saved in a new `source_url` column and shown on the result page and in history.
- Old databases get the new column added on start-up (`add_new_columns()` in `app/__init__.py`), because `db.create_all()` only creates missing tables and never adds columns. Nobody has to delete their `instance/jobcheck.db`.
- The page body is read in chunks with `iter_content()`, so a page over 2 MB is stopped early and connection errors while reading are caught.

## Before and after on real sites

Tested on 21 Nov 2026.

| Link | Before | After |
|---|---|---|
| Greenhouse board (GitLab, 50 postings) | 4,135 chars of titles and filter menus checked as one posting, no descriptions | detected as a listing, 10 postings opened and checked separately in about 6 s |
| Lever board (Palantir, 308 postings) | 20,000 chars of menus and titles, only the first 10,000 checked | detected as a listing, 10 opened in about 6 s, first 50 listed |
| Wellfound jobs page (47 postings) | whole page as one blob | detected as a listing, 10 opened in about 1 s |
| Internshala internships page | whole page as one blob | listing found from its JSON-LD `ItemList` |
| Greenhouse single posting | 12,441 chars including the application form, cut to 10,000 | 8,148 chars of just the posting, with line breaks |
| Wellfound single posting | 8,566 chars on one line | 6,794 chars from JSON-LD: title, company, description |
| Naukri, Indeed, foundit | same generic error | "the site blocked automated access (HTTP 403)" |

## The code, step by step

What happens when someone pastes a link (`check_url()` in `app/routes.py`):

1. `get_page(url)` calls `download(url)`, which checks the address is public, follows redirects one at a time (checking each), gives a clear error for 403/404/timeouts, and stops if the page is over 2 MB. `get_page` then parses the HTML with BeautifulSoup.
2. `posting_links(soup, url)` looks for links to separate postings (JSON-LD first, then `<a>` links that pass `looks_like_posting()`). If it finds 3 or more, the page is a listing.
3. **Single posting:** `posting_text(soup)` gets the text (JSON-LD `JobPosting` data if there is one, else the main part of the page, through `html_to_text()`). If it is long enough, it is checked with `save_check()` like pasted text and the user goes to the normal result page.
4. **Listing:** `check_listing()` reads robots.txt once with `get_robots()`, then loops over the links: skips the ones past the first 10 or blocked by robots.txt, opens the rest with `get_page()` and `posting_text()`, and saves each as its own check. Then it shows `listing.html`.

Helper functions in `app/fetch.py`:

| Function | What it does |
|---|---|
| `is_public_host(host)` | looks up the host's IP addresses and returns False for private ones (localhost, 10.x, 192.168.x, 169.254.x) |
| `download(url)` | safe download, returns final url, content type and body |
| `get_page(url)` | `download` + checks it is HTML + parses it |
| `read_json_ld(soup)` | reads every `<script type="application/ld+json">` block into Python dicts |
| `job_posting_text(job)` | turns one JobPosting dict into text: title, company, description |
| `html_to_text(node)` | HTML to text with a line break after each block tag |
| `posting_text(soup)` | picks the best text for the posting on a page |
| `looks_like_posting(url, page_url)` | the link-guessing rules above |
| `posting_links(soup, page_url)` | all posting links on a listing page, or `{}` for a single posting |
| `get_robots(page_url)` | reads robots.txt into Python's built-in `RobotFileParser` |

## Things to know when presenting

### Demo plan

1. Paste a Greenhouse or Lever job board link (for example `https://job-boards.greenhouse.io/gitlab`). Show the listing page: each posting checked on its own, the rest with "Check this one".
2. Click one result to show the full posting text with line breaks, and the "Text read from" link.
3. Paste a single posting link (a Wellfound or Internshala posting). Point out the title and company at the top, which come from the JSON-LD data.
4. Paste a Naukri link to show the clear "blocked" message and the paste fallback.
5. Open History to show the saved links.

Local test pages can't be used for the demo, because the app refuses to fetch `localhost` or private addresses. That is on purpose (see SSRF below). The tests get around it by pretending `127.0.0.1` is public.

Don't test the same site many times right before the demo. While testing, Internshala started refusing our connections after about 20 requests in a few minutes. That is also why we only open 10 postings, one at a time.

### Questions we might get

- **Is this scraping legal or ethical?** The app reads one public page the user asked for, like a browser would. When it opens links by itself it checks robots.txt, opens at most 10 pages one at a time, and sends an honest user agent (`JobCheckResearchBot`). It does not log in, solve captchas, rotate IPs or pretend to be a browser. If a site blocks us, we tell the user to paste the text.
- **Why not Selenium or Playwright for JavaScript sites?** It needs a full browser on the server, is slow (seconds per page) and heavy, and the big sites that need JavaScript (Naukri, Indeed, LinkedIn) block bots or need a login anyway. JSON-LD gets us the posting on many JavaScript-built sites without running any JavaScript.
- **What is SSRF and how is it handled?** Server-side request forgery: someone gives the server a link like `http://169.254.169.254/` (cloud metadata) or `http://localhost:5000/admin`, and the server fetches its own private network for them. `is_public_host()` resolves the host name and refuses anything that is not a public address, and redirects are followed by hand so each new address is checked too. One known gap is DNS rebinding (the name can resolve to a different address the second time); it is marked as a TODO in `download()` and would matter only on a public server.
- **How does it know a page is a listing?** JSON-LD first (`ItemList`, several `JobPosting`s, or exactly one `JobPosting` which means a single posting), then the link pattern described above. It is a heuristic, so there is a button to check the page as one posting if it guesses wrong.
- **Why 10 postings?** It keeps the wait to a few seconds and the load on the other site small. The rest are listed with a button to check them one by one.
- **Why not open them all at the same time (threads)?** It would be faster, but one at a time is simpler and gentler on the site, and 10 pages still only take a few seconds.

### Known limits

- Pages that need JavaScript and have no JSON-LD come back nearly empty, and the user is asked to paste the text.
- Sites whose posting links have no id (only a slug like `/careers/backend-engineer`) are not detected as listings, so the page is checked as one posting like before.
- Posting links on a different host name (for example a company site linking to its jobs on `greenhouse.io`) are not followed.
- The rules are written for English postings.

## Possible next steps

- Accept a `url` in the JSON API (`/api/check`) as well as `text`.
- Allow links in the bulk upload file.
- Use `posting_links()` in the data scrapers, so they save individual postings instead of page-level records (`scrape_pages.py` saves whole pages right now and says so in its notes column).
- Warn about the link itself: Google Forms, URL shorteners and `wa.me` links used as the "application page" are common in scams.
- Pin the checked IP address when fetching, to close the DNS rebinding gap before any public deployment.

## Files changed

| File | Change |
|---|---|
| `app/fetch.py` | rewritten: safe download with clear errors, JSON-LD reading, listing detection, robots.txt check |
| `app/routes.py` | `/check-url` handles single postings and listings, saves the link, warns about cut text |
| `app/forms.py` | `single` field on the URL form ("check the page as one posting") |
| `app/models.py` | `source_url` column on `checks` |
| `app/__init__.py` | adds `source_url` to existing databases on start-up |
| `app/templates/listing.html` | new: results for a listing page |
| `app/templates/result.html` | shows the link the text was read from |
| `app/templates/history.html` | shows the link under url checks |
| `app/templates/index.html` | updated help text under the link box |
| `tests/test_fetch.py` | tests for text extraction, JSON-LD, listing detection, robots.txt, error messages, the listing flow and the database upgrade |
| `README.md` | URL input section updated |
| `SCRAPING_README.md` | this file |

All 107 tests pass (`pytest`).
