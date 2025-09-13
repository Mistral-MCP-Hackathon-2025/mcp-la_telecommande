from dataclasses import dataclass


@dataclass
class VMCredentials:
    host: str
    user: str
    port: int
    key: str | None
