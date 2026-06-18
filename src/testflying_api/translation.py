from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from testflying_api.config import Settings
from testflying_api.errors import ApiError


def translate_store_metadata_text(
    settings: Settings,
    *,
    source_locale: str,
    target_locales: list[str],
    field: str,
    text: str,
) -> dict[str, str]:
    normalized_text = text.strip()
    normalized_targets = _unique_locales(target_locales, exclude=source_locale)
    if not normalized_text:
        raise ApiError("invalid_translation_text", "源文案不能为空", status_code=422)
    if not normalized_targets:
        return {}

    provider = settings.translation_provider.strip().lower()
    if provider in {"", "disabled", "none"}:
        raise ApiError(
            "translation_not_configured",
            "翻译服务未配置，无法生成多语言内容",
            status_code=503,
        )
    if provider == "mock":
        return {locale: f"{normalized_text} [{locale}]" for locale in normalized_targets}
    if provider == "openai":
        return _translate_with_openai(
            settings,
            source_locale=source_locale,
            target_locales=normalized_targets,
            field=field,
            text=normalized_text,
        )
    raise ApiError(
        "unsupported_translation_provider",
        f"不支持的翻译服务：{settings.translation_provider}",
        status_code=422,
    )


def _translate_with_openai(
    settings: Settings,
    *,
    source_locale: str,
    target_locales: list[str],
    field: str,
    text: str,
) -> dict[str, str]:
    if not settings.translation_openai_api_key:
        raise ApiError(
            "translation_not_configured",
            "翻译服务缺少 API Key",
            status_code=503,
        )
    payload = {
        "model": settings.translation_openai_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You translate App Store Connect and Google Play app metadata. "
                    "Return only JSON in this shape: "
                    '{"translations":{"locale-code":"translated text"}}. '
                    "Do not add explanations. Preserve URLs, placeholders, brand names, "
                    "line breaks, and comma-separated keyword format."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "sourceLocale": source_locale,
                        "targetLocales": target_locales,
                        "field": field,
                        "text": text,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }
    request = Request(
        settings.translation_openai_base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.translation_openai_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise ApiError(
            "translation_failed",
            f"翻译服务调用失败（HTTP {error.code}）",
            status_code=502,
        ) from error
    except (TimeoutError, URLError, json.JSONDecodeError) as error:
        raise ApiError(
            "translation_failed",
            "翻译服务调用失败，请稍后重试",
            status_code=502,
        ) from error

    content = _response_content(response_payload)
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as error:
        raise ApiError(
            "translation_failed",
            "翻译服务返回格式不正确",
            status_code=502,
        ) from error
    mapping = decoded.get("translations") if isinstance(decoded, dict) else None
    if not isinstance(mapping, dict):
        mapping = decoded if isinstance(decoded, dict) else {}
    translations = {
        locale: str(mapping.get(locale) or "").strip()
        for locale in target_locales
        if str(mapping.get(locale) or "").strip()
    }
    if not translations:
        raise ApiError(
            "translation_failed",
            "翻译服务没有返回可用译文",
            status_code=502,
        )
    return translations


def _response_content(response_payload: object) -> str:
    if not isinstance(response_payload, dict):
        return ""
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    return str(message.get("content") or "")


def _unique_locales(locales: list[str], *, exclude: str) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for locale in locales:
        value = str(locale or "").strip()
        if not value or value == exclude or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized
