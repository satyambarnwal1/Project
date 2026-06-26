"""Quick self-test of the offline logic (no network needed)."""

from harvester.config import Settings
from harvester.extractor import extract_emails, is_low_value
from harvester.query import SearchQuery, generate_queries
from harvester.crawler import SiteCrawler, registered_domain
import itertools

settings = Settings()
blocked = settings.blocked_email_substrings

SAMPLE_HTML = """
<html><body>
  <a href="mailto:Sales@AcmeRealty.com?subject=Hi">Email sales</a>
  <a href="mailto:info@acmerealty.com, hr@acmerealty.com">Multiple</a>
  <p>Reach our broker at jane.doe@acme-realty.co.uk for listings.</p>
  <p>Obfuscated: support [at] acmerealty [dot] com</p>
  <p>Also: contact(at)example(dot)com  &lt;- placeholder, should be dropped</p>
  <p>Entity-encoded: ceo&#64;acmerealty&#46;com</p>
  <img src="logo@2x.png"> sprite icon@3x.webp
  <p>Junk: hello@yourdomain.com and noreply@acmerealty.com</p>
  <a href="/about-us">About Us</a>
  <a href="/contact">Contact</a>
  <a href="/blog/2024/market">Market blog</a>
  <a href="https://twitter.com/acme">Twitter</a>
</body></html>
"""

print("=== 1. EMAIL EXTRACTION ===")
emails = extract_emails(SAMPLE_HTML, [
    "mailto:Sales@AcmeRealty.com?subject=Hi",
    "mailto:info@acmerealty.com, hr@acmerealty.com",
    "/about-us", "/contact",
], blocked)
for e in sorted(emails):
    flag = "  [low-value]" if is_low_value(e, settings.low_value_local_parts) else ""
    print(f"  {e}{flag}")

expected = {
    "sales@acmerealty.com", "info@acmerealty.com", "hr@acmerealty.com",
    "jane.doe@acme-realty.co.uk", "support@acmerealty.com",
    "ceo@acmerealty.com", "noreply@acmerealty.com",
}
junk_should_be_absent = {
    "logo@2x.png", "icon@3x.webp", "hello@yourdomain.com",
    "contact@example.com",
}
print("  missing (BAD if any):", expected - emails)
print("  junk leaked (BAD if any):", junk_should_be_absent & emails)

print("\n=== 2. CRAWLER LINK PRIORITISATION (offline) ===")
crawler = SiteCrawler(settings)
prio, other, hrefs = crawler._links(SAMPLE_HTML, "https://acmerealty.com/", "acmerealty.com")
print("  priority links:", prio)
print("  other links   :", other)
print("  registered_domain('https://www.acme-realty.co.uk/x') ->",
      registered_domain("https://www.acme-realty.co.uk/x"))

print("\n=== 3. QUERY GENERATION ===")
print("  -- country only (USA), first 6 --")
q1 = SearchQuery(industry="real estate", country="USA")
for s in itertools.islice(generate_queries(q1), 6):
    print("   ", s)
print("  -- with state+city, first 4 --")
q2 = SearchQuery(industry="real estate", country="USA",
                 state="California", district="Los Angeles")
for s in itertools.islice(generate_queries(q2), 4):
    print("   ", s)
print("  -- null-ish optional fields are ignored --")
q3 = SearchQuery(industry="law firms", country="USA",
                 state="null", district="", zip_code="N/A")
print("    base_location:", q3.base_location(), "(should be None)")
print("\nAll checks ran.")
