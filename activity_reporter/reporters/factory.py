from typing import TYPE_CHECKING

from activity_reporter.reporters.anthropic import AnthropicReportGenerator
from activity_reporter.reporters.base import ReportGenerationParameters, ReportGenerator
from activity_reporter.reporters.openai import OpenAIReportGenerator

if TYPE_CHECKING:
    from activity_reporter.config import ReportSettings


def build_report_generator(settings: "ReportSettings") -> ReportGenerator:
    parameters = ReportGenerationParameters(
        model=settings.model,
        max_events=settings.max_events,
        max_input_characters=settings.max_input_characters,
        max_tokens=settings.max_tokens,
    )
    generators = {
        "anthropic": AnthropicReportGenerator,
        "openai": OpenAIReportGenerator,
    }
    return generators[settings.provider](settings.api_key, parameters)
