from typing import Optional

from httpx import AsyncClient, Response
from tenacity import retry, stop_after_attempt, wait_fixed


def __get_async_client() -> AsyncClient:
    return AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:160.0) Gecko/20100101 Firefox/160.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://google.com"
        }
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(15),
    retry_error_callback=lambda error_state: None,
)
async def make_request(url: str, params: Optional[dict[str, str | int]]) -> Response:
    async with __get_async_client() as client:
        result = await client.get(url, params=params)
        if len(result.content) == 0:
            raise ValueError("Got blank response from the Lodestone!")
        return result

