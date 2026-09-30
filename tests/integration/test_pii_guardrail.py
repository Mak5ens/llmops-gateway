"""pii-fr guardrail: personal data is masked before the model and put back into the answer, per team.

Calls use LiteLLM's mock_response, which answers without calling the model but still runs the guardrail: a marker
in the mock answer comes back as the real value only if the prompt was masked with that marker.
"""

import httpx
from openai import OpenAI

DEMO = (
    "Je suis Marie Dupont, j'habite au 12 rue de la Paix, 75002 Paris. "
    "Mon IBAN est FR76 3000 6000 0112 3456 7890 189. Rappelez Marie Dupont au 06 12 34 56 78."
)


def answer(client: OpenAI, messages: list[dict], mock: str, alias: str = "chat-large", **extra) -> str:
    response = client.chat.completions.create(model=alias, messages=messages, extra_body={"mock_response": mock, **extra})
    return response.choices[0].message.content


def user(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def test_the_prompt_reaches_the_model_with_markers_only(admin: httpx.Client):
    # The admin endpoint runs the guardrail on a text and returns what the model would receive.
    response = admin.post("/guardrails/apply_guardrail", json={"guardrail_name": "pii-fr", "text": DEMO})
    response.raise_for_status()
    assert response.json()["response_text"] == (
        "Je suis <PERSON_1>, j'habite au <FR_ADDRESS_2>. Mon IBAN est <IBAN_CODE_3>. "
        "Rappelez <PERSON_1> au <PHONE_NUMBER_4>."
    )


def test_the_answer_comes_back_with_the_real_values(team_client):
    mock = "Dossier de <PERSON_1>, <FR_ADDRESS_2>, virement sur <IBAN_CODE_3>, joignable au <PHONE_NUMBER_4>."
    assert answer(team_client("baux"), user(DEMO), mock) == (
        "Dossier de Marie Dupont, 12 rue de la Paix, 75002 Paris, virement sur FR76 3000 6000 0112 3456 7890 189, "
        "joignable au 06 12 34 56 78."
    )


def test_two_people_in_two_messages_get_two_markers(team_client):
    messages = [
        {"role": "user", "content": "Le bailleur est Jean Martin."},
        {"role": "assistant", "content": "Noté."},
        {"role": "user", "content": "La locataire est Marie Dupont."},
    ]
    assert answer(team_client("baux"), messages, "<PERSON_1> loue à <PERSON_2>.") == "Jean Martin loue à Marie Dupont."


def test_a_streamed_answer_is_put_back_too(team_client):
    stream = team_client("baux").chat.completions.create(
        model="chat-large", messages=user(DEMO), stream=True, extra_body={"mock_response": "Bonjour <PERSON_1> !"}
    )
    chunks = [chunk.choices[0].delta.content or "" for chunk in stream if chunk.choices]
    assert "".join(chunks) == "Bonjour Marie Dupont !"


def test_an_opted_out_team_is_not_masked(team_client):
    # f1 is "optional" in config/tenants.yaml: the marker is not in the request, so it stays as is.
    assert answer(team_client("f1"), user(DEMO), "Bonjour <PERSON_1> !", alias="chat-small") == "Bonjour <PERSON_1> !"


def test_an_opted_out_team_can_mask_one_request(team_client):
    reply = answer(
        team_client("f1"), user(DEMO), "Bonjour <PERSON_1> !", alias="chat-small", guardrails=["pii-fr-on-request"]
    )
    assert reply == "Bonjour Marie Dupont !"


def test_a_required_team_cannot_opt_out_from_the_request(team_client):
    # The opt-out is read from the team metadata written by the admin, not from what the caller sends.
    spoofed = {"user_api_key_team_metadata": {"opted_out_global_guardrails": ["pii-fr"]}, "disable_global_guardrails": True}
    assert answer(team_client("baux"), user(DEMO), "Bonjour <PERSON_1> !", metadata=spoofed) == "Bonjour Marie Dupont !"
