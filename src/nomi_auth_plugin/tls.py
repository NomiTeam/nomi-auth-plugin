import ssl

from .config import Config


def create_context(config: Config) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=config.nomi_tls_ca_cert or None)
    if config.nomi_tls_client_cert:
        context.load_cert_chain(config.nomi_tls_client_cert, config.nomi_tls_client_key)
    return context


def is_certificate_error(error: BaseException) -> bool:
    visited: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in visited:
        if isinstance(current, ssl.SSLError):
            return True
        visited.add(id(current))
        current = current.__cause__ or current.__context__
    return False
