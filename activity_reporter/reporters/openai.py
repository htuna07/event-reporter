from openai import OpenAI

from activity_reporter.reporters.base import (
    BaseReportGenerator,
    REPORT_INSTRUCTIONS,
    ReportGenerationParameters,
)


class OpenAIReportGenerator(BaseReportGenerator):
    def __init__(self, api_key: str, parameters: ReportGenerationParameters) -> None:
        super().__init__(parameters)
        self.client = OpenAI(api_key=api_key)

    def _generate(self, input_data: str) -> str:
        response = self.client.responses.create(
            model=self.parameters.model,
            max_output_tokens=self.parameters.max_tokens,
            instructions=REPORT_INSTRUCTIONS,
            input=input_data,
        )
        return response.output_text
