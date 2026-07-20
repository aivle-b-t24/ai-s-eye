class ToolError(Exception):
    """Tool 실행 중 생기는 오류. message는 고객에게 그대로 전달해도 되는 문장이다."""

    code = "tool_error"
    message = "요청을 처리하지 못했습니다."


class StoreNotFoundError(ToolError):
    code = "store_not_found"
    message = "해당 매장의 상태 정보가 아직 없습니다."


class InvalidRequestError(ToolError):
    code = "invalid_request"
    message = "요청 형식이 올바르지 않습니다."


class SampleDataUnavailableError(ToolError):
    code = "sample_data_unavailable"
    message = "매장 자료를 불러오지 못했습니다."


class ApiUnavailableError(ToolError):
    code = "api_unavailable"
    message = "매장 시스템에 연결하지 못했습니다."


class UnexpectedResponseError(ToolError):
    code = "unexpected_response"
    message = "매장 시스템이 예상하지 못한 응답을 보냈습니다."
