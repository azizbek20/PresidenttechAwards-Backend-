"""Test doubles for the Claude migration. Nothing here talks to the network."""

from tests.fakes.anthropic_client import FakeAnthropic, message_response
from tests.fakes.assessments import make_assessment

__all__ = ["FakeAnthropic", "message_response", "make_assessment"]
