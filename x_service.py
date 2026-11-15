import tweepy
from typing import List, Dict, Tuple


MOCK_PROFILES = [
    {
        "x_user_id": "900000001",
        "username": "linh_embodied_ai",
        "display_name": "Linh Nguyen",
        "location": "Ho Chi Minh City, Vietnam",
        "bio": "Building low-cost 6-DoF robotic arms & Vision-Language-Action (VLA) models for SEA manufacturing. Ex-Robotics researcher.",
        "recent_tweets": (
            "- Just open-sourced our sim-to-real grasp dataset trained on 50k synthetic trajectories.\n"
            "- Hardware iteration #4 on our tactile gripper finally hits <2ms latency on Jetson Orin."
        ),
    },
    {
        "x_user_id": "900000002",
        "username": "arjun_llm_infra",
        "display_name": "Arjun Tan",
        "location": "Singapore",
        "bio": "Co-founder @KestrelInference | Optimizing speculative decoding & quantized KV-cache for edge GPUs.",
        "recent_tweets": (
            "- Cut p95 TTFT by 38% on Llama-3-70B using custom Triton kernels. Write-up coming tomorrow.\n"
            "- Hiring systems engineers in SG/VN who love CUDA and Rust."
        ),
    },
    {
        "x_user_id": "900000003",
        "username": "siti_ai_agents",
        "display_name": "Siti Rahmawati",
        "location": "Jakarta, Indonesia",
        "bio": "Founder building multi-agent developer workflows & automated code review tools for fintech teams in Southeast Asia.",
        "recent_tweets": (
            "- Benchmarked 12 open-weights models on AST-aware code patching. Small fine-tuned models beat frontier APIs on latency.\n"
            "- Looking to connect with AI founders across Jakarta and Singapore."
        ),
    },
]


class XOutreachClient:
    def __init__(
        self,
        bearer_token: str = "",
        api_key: str = "",
        api_secret: str = "",
        access_token: str = "",
        access_token_secret: str = "",
        dry_run: bool = True,
    ):
        self.dry_run = dry_run
        self.client = None
        if not dry_run and bearer_token.strip():
            self.client = tweepy.Client(
                bearer_token=bearer_token.strip(),
                consumer_key=api_key.strip() or None,
                consumer_secret=api_secret.strip() or None,
                access_token=access_token.strip() or None,
                access_token_secret=access_token_secret.strip() or None,
                wait_on_rate_limit=False,
            )

    def fetch_by_handles(self, handles: List[str]) -> Tuple[List[Dict], List[str]]:
        """Fetch user profile and up to 5 recent original tweets per handle."""
        if self.dry_run:
            return MOCK_PROFILES, []

        if not self.client:
            return [], ["X API client is not initialized. Please provide your X Bearer Token or enable Dry-Run Mode."]

        results = []
        errors = []
        for raw_handle in handles:
            clean_handle = raw_handle.strip().lstrip("@")
            if not clean_handle:
                continue
            try:
                user_resp = self.client.get_user(
                    username=clean_handle,
                    user_fields=["description", "location", "public_metrics"],
                )
                if not user_resp.data:
                    errors.append(f"Handle @{clean_handle} not found on X.")
                    continue

                u = user_resp.data
                tweets_resp = self.client.get_users_tweets(
                    id=u.id,
                    max_results=5,
                    exclude=["retweets", "replies"],
                )
                tweets_text = "\n".join(
                    [f"- {t.text}" for t in (tweets_resp.data or [])]
                ) or "(No recent original tweets found)"

                results.append({
                    "x_user_id": str(u.id),
                    "username": u.username,
                    "display_name": u.name,
                    "location": getattr(u, "location", "") or "",
                    "bio": getattr(u, "description", "") or "",
                    "recent_tweets": tweets_text,
                })
            except tweepy.TweepyException as e:
                errors.append(f"X API error fetching @{clean_handle}: {str(e)}")

        return results, errors

    def search_by_keyword(self, query: str, max_results: int = 10) -> Tuple[List[Dict], List[str]]:
        """Search recent tweets by domain keywords (Requires X API Basic or Pay-per-use credits)."""
        if self.dry_run:
            return MOCK_PROFILES, []

        if not self.client:
            return [], ["X API client is not initialized. Please provide your X Bearer Token or enable Dry-Run Mode."]

        results = []
        errors = []
        try:
            search_query = f"({query}) -is:retweet -is:reply lang:en"
            resp = self.client.search_recent_tweets(
                query=search_query,
                max_results=max(10, min(max_results, 20)),
                expansions=["author_id"],
                user_fields=["description", "location", "username", "name"],
            )
            users_map = {u.id: u for u in (resp.includes.get("users", []) if resp.includes else [])}
            seen_authors = set()

            for tweet in resp.data or []:
                uid = tweet.author_id
                if uid in seen_authors or uid not in users_map:
                    continue
                seen_authors.add(uid)
                u = users_map[uid]
                results.append({
                    "x_user_id": str(u.id),
                    "username": u.username,
                    "display_name": u.name,
                    "location": getattr(u, "location", "") or "",
                    "bio": getattr(u, "description", "") or "",
                    "recent_tweets": f"- {tweet.text}",
                })
        except tweepy.TweepyException as e:
            errors.append(f"X Search API error (requires active Pay-per-use credits or Basic tier): {str(e)}")

        return results, errors

    def send_direct_message(self, x_user_id: str, text: str) -> Tuple[str, str]:
        """
        Send a 1-on-1 Direct Message via X API v2.
        Returns: (status, error_message) -> 'SENT' | 'DM_CLOSED' | 'RATE_LIMITED' | 'FAILED'
        """
        if self.dry_run:
            return "SENT", ""

        if not self.client:
            return "FAILED", "Missing X OAuth 1.0a credentials."

        try:
            self.client.create_direct_message(
                participant_id=str(x_user_id),
                text=text,
            )
            return "SENT", ""
        except tweepy.Forbidden as e:
            return "DM_CLOSED", f"403 Forbidden: Recipient disabled DMs from non-followers or App lacks DM permission ({str(e)})"
        except tweepy.TooManyRequests as e:
            return "RATE_LIMITED", f"429 Rate Limit: X API DM rate limit reached ({str(e)})"
        except tweepy.TweepyException as e:
            return "FAILED", f"X API Error: {str(e)}"

    def fetch_incoming_replies(self, sent_user_ids: List[str]) -> Dict[str, str]:
        """Poll DM events to detect replies from contacted prospects."""
        if self.dry_run:
            if "900000001" in sent_user_ids:
                return {
                    "900000001": "Thanks for reaching out! Would love to chat about our VLA roadmap in SEA next week."
                }
            return {}

        if not self.client:
            return {}

        replies_map = {}
        try:
            me = self.client.get_me()
            my_id = str(me.data.id)
            events = self.client.get_direct_message_events(
                dm_event_fields=["sender_id", "text", "created_at"],
                max_results=50,
            )
            target_set = set(str(uid) for uid in sent_user_ids)
            for ev in events.data or []:
                sender = str(ev.sender_id)
                if sender != my_id and sender in target_set and sender not in replies_map:
                    replies_map[sender] = ev.text
        except tweepy.TweepyException:
            pass
        return replies_map
