from anthropic import Anthropic

from activity_reporter.reporters.base import (
    BaseReportGenerator,
    REPORT_INSTRUCTIONS,
    ReportGenerationParameters,
)


class AnthropicReportGenerator(BaseReportGenerator):
    def __init__(self, api_key: str, parameters: ReportGenerationParameters) -> None:
        super().__init__(parameters)
        self.client = Anthropic(api_key=api_key)

    def _generate(self, input_data: str) -> str:
        response = self.client.messages.create(
            model=self.parameters.model,
            max_tokens=self.parameters.max_tokens,
            system=REPORT_INSTRUCTIONS,
            messages=[{"role": "user", "content": input_data}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
