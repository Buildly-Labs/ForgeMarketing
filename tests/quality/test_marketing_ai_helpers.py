import dashboard.marketing_calendar_api as mca


def test_extract_ai_text_from_openai_shape():
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"summary":"ok"}'
                }
            }
        ]
    }
    assert mca._extract_ai_text(payload) == '{"summary":"ok"}'


def test_extract_ai_text_from_fallback_shapes():
    assert mca._extract_ai_text({"response": "hello"}) == "hello"
    assert mca._extract_ai_text({"output_text": "world"}) == "world"


def test_marketing_agent_config_defaults_present():
    url, token, model = mca._get_marketing_agent_config()
    assert isinstance(url, str)
    assert url
    assert isinstance(token, str)
    assert isinstance(model, str)
