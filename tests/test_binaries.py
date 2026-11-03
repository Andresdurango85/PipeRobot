"""Binary discovery preserves local skips and fails closed in CI."""

import pytest
from binaries import find_binary


@pytest.mark.parametrize("available", [{"pwsh", "powershell"}, {"powershell"}])
def test_find_binary_returns_first_match(available: set[str]) -> None:
    calls: list[str] = []

    def which(name: str) -> str | None:
        calls.append(name)
        return f"/bin/{name}" if name in available else None

    expected = "pwsh" if "pwsh" in available else "powershell"
    assert find_binary("pwsh", "powershell", env={}, which=which) == f"/bin/{expected}"
    assert calls == (["pwsh"] if expected == "pwsh" else ["pwsh", "powershell"])


@pytest.mark.parametrize("env", [{}, {"CI": "false"}])
def test_find_binary_skips_locally(env: dict[str, str]) -> None:
    with pytest.raises(pytest.skip.Exception, match="none of pwsh, powershell found on PATH"):
        find_binary("pwsh", "powershell", env=env, which=lambda name: None)


@pytest.mark.parametrize("ci", ["true", "TRUE"])
def test_find_binary_fails_in_ci(ci: str) -> None:
    with pytest.raises(
        pytest.fail.Exception,
        match="none of pwsh, powershell found on PATH; CI must run these tests",
    ):
        find_binary("pwsh", "powershell", env={"CI": ci}, which=lambda name: None)
