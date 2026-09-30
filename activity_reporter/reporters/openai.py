from openai import OpenAI

from activity_reporter.reporters.base import (
    BaseReportGenerator,
    REPORT_INSTRUCTIONS,
    ReportGenerationParameters,
)
from activity_reporter.logging import get_logger

logger = get_logger(__name__)


class OpenAIReportGenerator(BaseReportGenerator):
    def __init__(self, api_key: str, parameters: ReportGenerationParameters) -> None:
        super().__init__(parameters)
        self.client = OpenAI(api_key=api_key)

    def _generate(self, input_data: str) -> str:
        logger.debug(
            "openai.request_started",
            model=self.parameters.model,
            max_tokens=self.parameters.max_tokens,
        )
        response = self.client.responses.create(
            model=self.parameters.model,
            max_output_tokens=self.parameters.max_tokens,
            instructions=REPORT_INSTRUCTIONS,
            input=input_data,
        )
        logger.log("openai.request_completed", output_characters=len(response.output_text))
        return response.output_text
