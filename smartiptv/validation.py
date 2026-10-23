"""Local form validation. No requests or credential persistence."""

from urllib.parse import urlsplit


def server_error(value: str) -> str | None:
    value = value.strip()
    if not value:
        return "Informe o endereço do servidor."
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "Use um endereço com http:// ou https://."
        if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
            return "Confira o endereço do servidor."
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            return "Use apenas o servidor. Preencha usuário e senha abaixo."
        if parsed.path.rstrip("/").lower().endswith(("get.php", "player_api.php")):
            return "Informe a URL base, sem get.php ou player_api.php."
        if port is not None and port < 1:
            return "Confira a porta do servidor."
    except ValueError:
        return "Confira o endereço e a porta do servidor."
    return None
