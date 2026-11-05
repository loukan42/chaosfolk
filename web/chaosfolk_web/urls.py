"""Accept only public http(s) targets so a submitted URL cannot reach the server's own network."""
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".test", ".invalid", ".example")
ALLOWED_PORTS = {None, 80, 443}


class RejectedUrl(ValueError):
    pass


def normalize(raw):
    """Return a canonical URL string and its host, or raise RejectedUrl with a message for the visitor."""
    text = (raw or "").strip()
    if not text or len(text) > 2000:
        raise RejectedUrl("Enter the address of your site.")
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        raise RejectedUrl("This address is not valid.") from None
    if parts.scheme not in {"http", "https"}:
        raise RejectedUrl("Only http and https addresses are accepted.")
    if parts.username or parts.password:
        raise RejectedUrl("Remove the user name or password from the address.")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host or host == "localhost" or host.endswith(BLOCKED_SUFFIXES) or "." not in host and ":" not in host:
        raise RejectedUrl("Enter a public address, not a local one.")
    if port not in ALLOWED_PORTS:
        raise RejectedUrl("Only the standard ports 80 and 443 are accepted.")
    try:
        host.encode("idna")
    except UnicodeError:
        raise RejectedUrl("This address is not valid.") from None
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, "")), host


def is_public(address):
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_public(host, resolver=socket.getaddrinfo):
    """Every address the host resolves to must be public; one private answer is enough to refuse."""
    try:
        answers = resolver(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise RejectedUrl("This site cannot be found. Check the address.") from None
    addresses = {answer[4][0] for answer in answers}
    if not addresses or not all(is_public(address) for address in addresses):
        raise RejectedUrl("Enter a public address, not a local one.")
    return sorted(addresses)


def validate(raw, resolver=socket.getaddrinfo):
    url, host = normalize(raw)
    check_public(host, resolver)
    return url, host
