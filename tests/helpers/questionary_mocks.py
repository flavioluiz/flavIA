"""Mock helpers for testing questionary-based prompts.

These helpers make it easy to mock questionary prompts in tests while
maintaining compatibility with the fallback mechanisms.
"""

from contextlib import contextmanager
from typing import Any, Iterator, Sequence
from unittest.mock import MagicMock, patch


@contextmanager
def mock_q_select(return_value: str) -> Iterator[MagicMock]:
    """Mock q_select to return a fixed value.

    Args:
        return_value: The value that q_select should return

    Yields:
        The mock object for assertions
    """
    with patch("flavia.setup.prompt_utils.q_select", return_value=return_value) as mock:
        yield mock


@contextmanager
def mock_q_autocomplete(return_value: str) -> Iterator[MagicMock]:
    """Mock q_autocomplete to return a fixed value.

    Args:
        return_value: The value that q_autocomplete should return

    Yields:
        The mock object for assertions
    """
    with patch(
        "flavia.setup.prompt_utils.q_autocomplete", return_value=return_value
    ) as mock:
        yield mock


@contextmanager
def mock_q_confirm(return_value: bool) -> Iterator[MagicMock]:
    """Mock q_confirm to return a fixed value.

    Args:
        return_value: The boolean value that q_confirm should return

    Yields:
        The mock object for assertions
    """
    with patch("flavia.setup.prompt_utils.q_confirm", return_value=return_value) as mock:
        yield mock


@contextmanager
def mock_q_path(return_value: str) -> Iterator[MagicMock]:
    """Mock q_path to return a fixed value.

    Args:
        return_value: The path string that q_path should return

    Yields:
        The mock object for assertions
    """
    with patch("flavia.setup.prompt_utils.q_path", return_value=return_value) as mock:
        yield mock


@contextmanager
def mock_q_password(return_value: str) -> Iterator[MagicMock]:
    """Mock q_password to return a fixed value.

    Args:
        return_value: The password string that q_password should return

    Yields:
        The mock object for assertions
    """
    with patch("flavia.setup.prompt_utils.q_password", return_value=return_value) as mock:
        yield mock


@contextmanager
def mock_q_checkbox(return_value: list[str]) -> Iterator[MagicMock]:
    """Mock q_checkbox to return a fixed list of values.

    Args:
        return_value: The list of selected values that q_checkbox should return

    Yields:
        The mock object for assertions
    """
    with patch("flavia.setup.prompt_utils.q_checkbox", return_value=return_value) as mock:
        yield mock


def mock_non_interactive(monkeypatch) -> None:
    """Force non-interactive mode in tests.

    This patches is_interactive() to always return False, ensuring
    the fallback prompt mechanisms are used.

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr("flavia.setup.prompt_utils.is_interactive", lambda: False)


def mock_interactive(monkeypatch) -> None:
    """Force interactive mode in tests.

    This patches is_interactive() to always return True, ensuring
    questionary prompts are used (if available).

    Args:
        monkeypatch: pytest monkeypatch fixture
    """
    monkeypatch.setattr("flavia.setup.prompt_utils.is_interactive", lambda: True)


class MockQuestionarySelect:
    """Mock for questionary.select() that returns a predetermined value."""

    def __init__(self, return_value: str):
        self.return_value = return_value
        self.message = None
        self.choices = None
        self.default = None

    def __call__(self, message: str, choices: Sequence[Any], default: Any = None):
        self.message = message
        self.choices = choices
        self.default = default
        return self

    def ask(self) -> str:
        return self.return_value


class MockQuestionaryConfirm:
    """Mock for questionary.confirm() that returns a predetermined value."""

    def __init__(self, return_value: bool):
        self.return_value = return_value
        self.message = None
        self.default = None

    def __call__(self, message: str, default: bool = False):
        self.message = message
        self.default = default
        return self

    def ask(self) -> bool:
        return self.return_value


class MockQuestionaryCheckbox:
    """Mock for questionary.checkbox() that returns a predetermined list."""

    def __init__(self, return_value: list[str]):
        self.return_value = return_value
        self.message = None
        self.choices = None

    def __call__(self, message: str, choices: Sequence[Any]):
        self.message = message
        self.choices = choices
        return self

    def ask(self) -> list[str]:
        return self.return_value


class MockQuestionaryAutocomplete:
    """Mock for questionary.autocomplete() that returns a predetermined value."""

    def __init__(self, return_value: str):
        self.return_value = return_value
        self.message = None
        self.choices = None
        self.default = None

    def __call__(
        self,
        message: str,
        choices: Sequence[str],
        default: str = "",
        match_middle: bool = True,
        ignore_case: bool = True,
    ):
        self.message = message
        self.choices = choices
        self.default = default
        return self

    def ask(self) -> str:
        return self.return_value


@contextmanager
def mock_questionary_module(
    select_value: str | None = None,
    confirm_value: bool | None = None,
    checkbox_value: list[str] | None = None,
    autocomplete_value: str | None = None,
) -> Iterator[MagicMock]:
    """Mock the entire questionary module for comprehensive testing.

    Args:
        select_value: Return value for questionary.select()
        confirm_value: Return value for questionary.confirm()
        checkbox_value: Return value for questionary.checkbox()
        autocomplete_value: Return value for questionary.autocomplete()

    Yields:
        Mock module object
    """
    mock_module = MagicMock()

    if select_value is not None:
        mock_module.select = MockQuestionarySelect(select_value)
        mock_module.Choice = MagicMock(side_effect=lambda title, value: MagicMock(
            title=title, value=value
        ))

    if confirm_value is not None:
        mock_module.confirm = MockQuestionaryConfirm(confirm_value)

    if checkbox_value is not None:
        mock_module.checkbox = MockQuestionaryCheckbox(checkbox_value)
        mock_module.Choice = MagicMock(side_effect=lambda title, value, checked=False: MagicMock(
            title=title, value=value, checked=checked
        ))

    if autocomplete_value is not None:
        mock_module.autocomplete = MockQuestionaryAutocomplete(autocomplete_value)

    with patch.dict("sys.modules", {"questionary": mock_module}):
        yield mock_module
