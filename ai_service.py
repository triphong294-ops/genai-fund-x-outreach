from google import genai
from google.genai import types
from pydantic import BaseModel, Field


class OutreachEvaluation(BaseModel):
    is_fit: bool = Field(
        description="True if the person is a builder, founder, researcher, or engineer working on AI models, applications, dev tools, infrastructure, robotics, or embodied AI."
    )
    fit_reason: str = Field(
        description="Concise 1-2 sentence explanation of why they are relevant to GenAI Fund's Southeast Asia AI & Robotics ecosystem."
    )
    evidence_quote: str = Field(
        description="Verbatim quote or specific factual detail extracted strictly from their Bio or recent Tweets."
    )
    personalized_dm: str = Field(
        description="Natural, non-salesy 1-on-1 DM under 260 characters referencing the evidence_quote directly, with zero invented familiarity."
    )


def analyze_and_draft_dm(
    api_key: str,
    display_name: str,
    username: str,
    bio: str,
    location: str,
    recent_tweets: str,
    model_name: str = "gemini-3.5-flash",
) -> OutreachEvaluation:
    client = genai.Client(api_key=api_key.strip())

    prompt = f"""
You are an Ecosystem & Talent Associate at GenAI Fund — a venture fund building AI and robotics ecosystems across Southeast Asia.

Task: Evaluate the X (Twitter) profile below and draft a warm, personalized 1-on-1 DM to start a genuine conversation.

CANDIDATE PROFILE:
- Name: {display_name} (@{username})
- Location: {location}
- Bio: {bio}
- Recent Original Posts (Tweets):
{recent_tweets}

STRICT GUARDRAILS:
1. Grounding: Use ONLY verifiable facts present in the Bio or Recent Posts above. Never fabricate projects, papers, or pretend you have met/spoken before.
2. Relevance Filter: If the profile is unrelated to AI, ML, DevTools, AI Infra, or Robotics/Embodied AI, set is_fit = false.
3. Tone & Length: Write in natural, peer-to-peer English under 260 characters. Reference their specific technical work directly and open a light conversation around GenAI Fund's SEA ecosystem. Avoid generic fluff ("I hope this finds you well", "synergy", "revolutionary").
"""

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=OutreachEvaluation,
        temperature=0.35,
    )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=config,
        )
    except Exception:
        # Graceful fallback if the selected preview/newer model is unavailable on the user's API key
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )

    return OutreachEvaluation.model_validate_json(response.text)
