"""Bounded HTTPS GET pinned to a verified public peer. No redirects are followed."""
import http.client
import ipaddress
import socket
import ssl
import time
from urllib.parse import quote, urlencode

from .runs import ROOT, now, sha256

ALLOWED_HOSTS = {'classification.psa.gov.ph', 'www.pangasinan.gov.ph', 'download.geofabrik.de'}
MAX_BYTES = 5_000_000
TIMEOUT = 25
USER_AGENT = 'BetterPangasinanCollector/1 (civic research; review-only)'


class FetchError(Exception):
    """Carries a short machine-readable code; never includes credentials."""


def public_addresses(host, resolver=socket.getaddrinfo):
    addresses = {str(row[4][0]) for row in resolver(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise FetchError('nonpublic_destination')
    return sorted(addresses, key=lambda ip: (ipaddress.ip_address(ip).version, ip))


def read_token():
    """PSA token from the environment or .env (parsed as data, never executed)."""
    import os
    value = os.environ.get('PSA-TOKEN') or os.environ.get('PSA_TOKEN')
    if value is None:
        env = ROOT / '.env'
        values = []
        if env.is_file():
            for line in env.read_text().splitlines():
                key, sep, raw = line.partition('=')
                if sep and key.strip() in ('PSA-TOKEN', 'PSA_TOKEN'):
                    values.append(raw.strip().strip('"\''))
        if len(values) != 1:
            raise FetchError('credential_configuration')
        value = values[0]
    if not value or any(c.isspace() for c in value):
        raise FetchError('credential_configuration')
    return value


def redact(data, secret):
    if not secret:
        return data
    for form in {secret, quote(secret, safe=''), quote(secret)}:
        data = data.replace(form.encode(), b'[REDACTED]')
    return data


def _open(host, path_and_query, accept):
    """Pinned TLS connection to a verified public peer; returns (connection, response, peer)."""
    if host not in ALLOWED_HOSTS:
        raise FetchError('destination_not_allowlisted')
    ip = public_addresses(host)[0]
    connection = http.client.HTTPSConnection(host, timeout=TIMEOUT)
    raw_socket = socket.create_connection((ip, 443), timeout=TIMEOUT)
    connection.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=host)
    peer = connection.sock.getpeername()[0]
    if ipaddress.ip_address(peer) != ipaddress.ip_address(ip):
        connection.close()
        raise FetchError('peer_mismatch')
    connection.request('GET', path_and_query, headers={'Accept': accept, 'User-Agent': USER_AGENT})
    return connection, connection.getresponse(), peer


def get(host, path, query=None, secret=None, accept='application/json', max_bytes=MAX_BYTES):
    """Return (artifact_bytes, evidence_meta). The recorded URL never contains the secret."""
    if not path.startswith('/'):
        raise FetchError('destination_not_allowlisted')
    query = dict(query or {})
    public_query = urlencode(query)
    source_url = f'https://{host}{path}' + (f'?{public_query}' if public_query else '')
    if secret:
        query['token'] = secret
    started = time.monotonic()
    connection = None
    try:
        connection, response, peer = _open(host, path + (f'?{urlencode(query)}' if query else ''), accept)
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise FetchError('response_size_limit')
        if time.monotonic() - started > TIMEOUT * 2:
            raise FetchError('time_limit')
        artifact = redact(body, secret)
        return artifact, {
            'source_url': source_url, 'retrieved_at': now(), 'http_status': response.status,
            'content_type': response.getheader('Content-Type'), 'location': response.getheader('Location'),
            'peer_ip': peer, 'response_sha256': sha256(body), 'artifact_redacted': artifact != body,
        }
    except (OSError, ssl.SSLError, http.client.HTTPException) as error:
        raise FetchError(type(error).__name__) from None
    finally:
        if connection:
            connection.close()


def download(host, path, dest, max_bytes, max_seconds=1800):
    """Stream a large file to dest (must not exist) with size/time limits; returns evidence meta."""
    import hashlib
    from pathlib import Path
    dest = Path(dest)
    partial = dest.with_suffix(dest.suffix + '.part')
    digest, size, started, connection = hashlib.sha256(), 0, time.monotonic(), None
    try:
        connection, response, peer = _open(host, path, '*/*')
        if response.status != 200:
            raise FetchError(f'http_{response.status}')
        with open(partial, 'xb') as stream:
            while chunk := response.read(1 << 20):
                size += len(chunk)
                if size > max_bytes:
                    raise FetchError('response_size_limit')
                if time.monotonic() - started > max_seconds:
                    raise FetchError('time_limit')
                digest.update(chunk)
                stream.write(chunk)
        partial.rename(dest)
        return {'source_url': f'https://{host}{path}', 'retrieved_at': now(), 'http_status': response.status,
                'content_type': response.getheader('Content-Type'), 'peer_ip': peer,
                'last_modified': response.getheader('Last-Modified'), 'bytes': size,
                'response_sha256': digest.hexdigest()}
    except (OSError, ssl.SSLError, http.client.HTTPException) as error:
        raise FetchError(type(error).__name__) from None
    finally:
        partial.unlink(missing_ok=True)
        if connection:
            connection.close()
