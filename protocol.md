# Access Guard Protocol

- `verify_access(token: str) -> bool` MUST fail closed and return `False` if `token` is empty or whitespace-only.
- `verify_access(token: str) -> bool` MUST return `True` if and only if `token.startswith("valid_")`.
