"""Web and API commands: weather lookups, YouTube playback."""

from __future__ import annotations

import logging

from shared import config
from shared.schemas import CommandResult, Severity

logger = logging.getLogger(__name__)

# Words that carry no geographic meaning — stripped when extracting city names.
_WEATHER_STOP_WORDS = frozenset(
    [
        "weather",
        "in",
        "of",
        "what",
        "is",
        "the",
        "whats",
        "tell",
        "me",
        "about",
        "for",
        "check",
    ]
)


def get_weather(query: str) -> CommandResult:
    """Fetch and return the current weather for a city via OpenWeatherMap.

    Args:
        query: The user's voice command containing the city name.
    """
    try:
        import requests
    except ImportError:
        logger.error("requests is not installed.")
        return CommandResult(
            text="The requests library is not installed.",
            severity=Severity.ERROR,
            source="web_services",
        )

    import string

    query_no_punct = query.translate(str.maketrans("", "", string.punctuation))
    words = query_no_punct.lower().split()
    city_parts = [w for w in words if w not in _WEATHER_STOP_WORDS]
    city = " ".join(city_parts).strip()

    if not city:
        return CommandResult(
            text="Please tell me a city name to check the weather for.",
            severity=Severity.WARNING,
            source="web_services",
        )

    try:
        response = requests.get(
            config.WEATHER_BASE_URL,
            params={
                "q": city,
                "appid": config.WEATHER_API_KEY,
                "units": "metric",
            },
            timeout=10,
        )

        if response.status_code != 200:
            logger.warning(
                'Weather API returned status %d for city "%s".',
                response.status_code,
                city,
            )
            return CommandResult(
                text=f"I could not find weather data for {city}. Please try again.",
                severity=Severity.WARNING,
                source="web_services",
            )

        data = response.json()
        temp = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        description = data["weather"][0]["description"]

        text = (
            f"The temperature in {city} is {temp} degrees Celsius "
            f"with {description}. Humidity is {humidity} percent."
        )
        return CommandResult(text=text, source="web_services")

    except requests.ConnectionError:
        logger.warning("Weather API connection error.")
        return CommandResult(
            text="I cannot connect to the weather service. Check your internet connection.",
            severity=Severity.ERROR,
            source="web_services",
        )
    except requests.Timeout:
        logger.warning("Weather API request timed out.")
        return CommandResult(
            text="The weather service took too long to respond.",
            severity=Severity.ERROR,
            source="web_services",
        )
    except KeyError as exc:
        logger.error("Weather API response missing key: %s", exc)
        return CommandResult(
            text="I received an unexpected response from the weather service.",
            severity=Severity.ERROR,
            source="web_services",
        )
    except Exception as exc:
        logger.error("Weather lookup error: %s", exc)
        return CommandResult(
            text="Sorry, I could not fetch the weather information.",
            severity=Severity.ERROR,
            source="web_services",
        )


def wikipedia_search(query: str) -> CommandResult:
    """Search Wikipedia and return a two-sentence summary.

    Args:
        query: The user's voice command containing the search topic.
    """
    try:
        import wikipedia
    except ImportError:
        logger.error("wikipedia is not installed.")
        return CommandResult(
            text="The Wikipedia library is not installed.",
            severity=Severity.ERROR,
            source="web_services",
        )

    search_term = query.lower().replace("wikipedia", "").strip()
    if not search_term:
        return CommandResult(
            text="Please tell me what to search on Wikipedia.",
            severity=Severity.WARNING,
            source="web_services",
        )

    try:
        results = wikipedia.summary(search_term, sentences=2)
        return CommandResult(text=results, source="web_services")
    except wikipedia.DisambiguationError as exc:
        logger.info("Wikipedia disambiguation: %s", exc)
        return CommandResult(
            text="There are multiple results. Please be more specific.",
            severity=Severity.WARNING,
            source="web_services",
        )
    except Exception as exc:
        logger.error("Wikipedia search error: %s", exc)
        return CommandResult(
            text="Sorry, I could not find anything on Wikipedia.",
            severity=Severity.ERROR,
            source="web_services",
        )
