import asyncio
import logging
import erniebot
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

erniebot.api_type = 'aistudio'
erniebot.access_token = os.getenv("BAIDU_ACCESS_TOKEN")


async def verify_macro_volatility(latest_news_text: str) -> tuple[bool, str]:
    """Evaluates news text to determine if auto-execution should be blocked."""
    if not latest_news_text:
        return False, "No data"

    logger.info("Macro Gatekeeper evaluating: '%.60s...'", latest_news_text)

    prompt = (
        f"Analyze this news: '{latest_news_text}'. "
        "If it introduces extreme macro volatility (Trump policies, Fed meetings, SEC news), "
        "reply in this EXACT format: VOLATILE | [Short Reason]. "
        "Example: VOLATILE | Trump Tariff Announcement. "
        "If safe, reply: CLEAR | SAFE."
    )

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                erniebot.ChatCompletion.create,
                model='ernie-3.5',
                messages=[{'role': 'user', 'content': prompt}]
            )
            result = response.get_result().strip()
            is_volatile = "VOLATILE" in result
            logger.info("Gatekeeper result: %s", result)
            return is_volatile, result
        except Exception as e:
            if attempt == 2:
                logger.error("Gatekeeper API timeout: %s", e)
                return True, "API_FAILURE_DEFAULT_VOLATILE"
            await asyncio.sleep(2)

    return True, "API_FAILURE_DEFAULT_VOLATILE"