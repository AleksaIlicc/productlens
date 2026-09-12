# URL normalization shared by every provider, so the same page found twice
# (different engines, different tracking params) dedupes to one candidate.

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Params that never identify a product, only the click that brought us there.
TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "hsa_", "ef_", "_hs")
TRACKING_PARAMS = {
    "srsltid",
    "gclid",
    "gbraid",
    "wbraid",
    "gad_source",
    "gclsrc",
    "fbclid",
    "igshid",
    "msclkid",
    "yclid",
    "twclid",
    "ttclid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "_gl",
    "ref",
    "ref_src",
    "referrer",
    "source",
    "spm",
    "th",
    "psc",
}

REGIONAL_TLDS = {"hr", "ba", "me", "si", "mk", "bg", "ro", "al"}


def _strip_port(host: str) -> str:
    return host.split(":", 1)[0] if host.count(":") == 1 else host


def canonicalize(url: str) -> str:
    # Stable page identity: lowercase host, no www, no tracking, no fragment.
    if not url:
        return ""
    raw = url.strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    if "://" not in raw:
        raw = "https://" + raw

    parts = urlsplit(raw)
    host = _strip_port(parts.netloc.lower())
    if host.startswith("www."):
        host = host[4:]

    keep = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS
        and not k.lower().startswith(TRACKING_PREFIXES)
    ]
    keep.sort()

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    scheme = "https" if parts.scheme in ("http", "https", "") else parts.scheme
    return urlunsplit((scheme, host, path, urlencode(keep), ""))


def domain_of(url: str) -> str:
    host = _strip_port(urlsplit(canonicalize(url)).netloc.lower())
    return host[4:] if host.startswith("www.") else host


def tld_of(url: str) -> str:
    domain = domain_of(url)
    return domain.rsplit(".", 1)[-1] if "." in domain else ""


def region_of(url: str) -> str:
    # From the hostname alone; callers may refine it.
    domain = domain_of(url)
    if domain.endswith(".rs") or domain == "rs":
        return "rs"
    if domain.rsplit(".", 1)[-1] in REGIONAL_TLDS:
        return "regional"
    return "world"


def absolutize(base: str, maybe_relative: str) -> str:
    if not maybe_relative:
        return ""
    candidate = maybe_relative.strip()
    if candidate.startswith("//"):
        return "https:" + candidate
    if candidate.startswith(("http://", "https://", "data:")):
        return candidate
    try:
        return urljoin(base, candidate)
    except ValueError:
        return ""
