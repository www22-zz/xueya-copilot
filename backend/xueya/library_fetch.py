"""Bounded public-web snapshots. DNS addresses are checked and pinned per hop."""
import http.client
import ipaddress
import socket
import ssl
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from .common import AppError, require

MAX_BYTES = 1_048_576


def public_target(url):
    require(isinstance(url, str) and len(url) <= 2048 and not any(ord(c) < 33 for c in url), 'INVALID_PUBLIC_URL')
    try:
        target = urlsplit(url)
        port = target.port or (443 if target.scheme == 'https' else 80)
        require(target.scheme in ('https', 'http') and target.hostname and not target.username and not target.password and port in (80, 443), 'INVALID_PUBLIC_URL')
        host = target.hostname.encode('idna').decode('ascii')
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        require(literal is None or literal.is_global, 'PRIVATE_URL_FORBIDDEN')
        require('%' not in host, 'PRIVATE_URL_FORBIDDEN')
        require(host != 'localhost' and not host.endswith(('.local', '.localhost', '.internal')), 'PRIVATE_URL_FORBIDDEN')
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        require(addresses and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses), 'PRIVATE_URL_FORBIDDEN')
        # Connect to this numeric address, never resolve the hostname a second time.
        return target, host, port, addresses[0][4][0]
    except (ValueError, UnicodeError, socket.gaierror) as error:
        raise AppError('URL_RESOLUTION_FAILED') from error


class Extractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip, self.parts, self.title, self.in_title = 0, [], [], False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg', 'iframe'):
            self.skip += 1
        if tag == 'title':
            self.in_title = True
        if tag in ('p', 'div', 'br', 'section', 'li', 'h1', 'h2', 'h3', 'tr') and not self.skip:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg', 'iframe'):
            self.skip = max(0, self.skip-1)
        if tag == 'title':
            self.in_title = False
        if tag in ('p', 'div', 'section', 'li', 'h1', 'h2', 'h3', 'tr') and not self.skip:
            self.parts.append('\n')

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        elif not self.skip:
            self.parts.append(data)


def fetch_snapshot(url):
    deadline, original = time.monotonic()+20, url
    for hop in range(4):
        target, host, port, address = public_target(url)
        remaining = deadline-time.monotonic()
        require(remaining > 0, 'URL_TIMEOUT')
        connection = http.client.HTTPConnection(host, port, timeout=min(8, remaining))
        try:
            sock = socket.create_connection((address, port), timeout=min(8, remaining))
            connection.sock = sock
            if target.scheme == 'https':
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
            connection.sock = sock
            path = urlunsplit(('', '', target.path or '/', target.query, ''))
            connection.request('GET', path, headers={'Host': host if port in (80, 443) else f'{host}:{port}',
                               'User-Agent': 'XueyaCopilot/2.0 public-course-import', 'Accept': 'text/html,text/plain', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                require(hop < 3 and response.getheader('Location'), 'URL_REDIRECT_LIMIT')
                url = urljoin(url, response.getheader('Location'))
                continue
            require(response.status == 200, 'URL_NOT_ACCESSIBLE')
            require(response.getheader('Content-Encoding', 'identity').lower() == 'identity', 'URL_ENCODING_UNSUPPORTED')
            mime = response.headers.get_content_type()
            require(mime in ('text/html', 'text/plain'), 'URL_CONTENT_UNSUPPORTED')
            length = response.getheader('Content-Length')
            require(length is None or length.isdigit() and int(length) <= MAX_BYTES, 'URL_TOO_LARGE')
            chunks, size = [], 0
            while True:
                require(time.monotonic() < deadline, 'URL_TIMEOUT')
                chunk = response.read1(min(65536, MAX_BYTES+1-size))
                if not chunk:
                    break
                size += len(chunk)
                require(size <= MAX_BYTES, 'URL_TOO_LARGE')
                chunks.append(chunk)
            try:
                raw = b''.join(chunks).decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
            except LookupError as error:
                raise AppError('URL_ENCODING_UNSUPPORTED') from error
            title, text = host, raw
            if mime == 'text/html':
                parser = Extractor()
                parser.feed(raw)
                title = ''.join(parser.title).strip()[:160] or host
                text = '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
            require(text.strip() and len(text.encode('utf-8')) <= MAX_BYTES, 'URL_EMPTY_OR_TOO_LARGE')
            return {'text': text, 'title': title, 'originalUrl': original, 'finalUrl': url}
        except (OSError, http.client.HTTPException) as error:
            raise AppError('URL_FETCH_FAILED') from error
        finally:
            connection.close()
    raise AppError('URL_REDIRECT_LIMIT')
