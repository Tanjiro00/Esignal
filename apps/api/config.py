from dataclasses import asdict, dataclass
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class ImprovementFeatureFlags:
    """Kill switches for the product-improvement slices.

    Every capability remains disabled by default and must preserve the previous
    user experience until its slice is explicitly enabled.
    """

    earlyness_timeline: bool
    signal_review_queue: bool
    comment_topic_relevance: bool
    decision_experience: bool
    microtopic_content_gap: bool
    feedback_evaluation: bool
    topic_snapshot_buckets: bool
    channel_profile_feasibility_v2: bool
    outcome_suggestions: bool
    signal_packaging: bool
    youtube_oauth_analytics: bool
    query_expansion: bool
    ux_today_home_v1: bool
    ux_decision_card_v1: bool
    ux_simple_scores_v1: bool
    ux_simplified_navigation_v1: bool
    ux_onboarding_v2: bool
    ux_opportunity_detail_v2: bool
    ux_brief_v2: bool
    ux_results_v2: bool
    llm_intelligence: bool

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


class Settings(BaseSettings):
    app_env: str = "development"
    demo_mode: bool = True
    database_url: str = "sqlite:///./earlysignal.db"
    redis_url: str = "redis://localhost:6379/0"
    web_origin: str = "http://localhost:3000"
    auth_required: bool = False
    auth_cookie_name: str = "earlysignal_session"
    auth_cookie_secure: bool = False
    auth_session_days: int = 30
    auth_password_iterations: int = 600_000
    auth_login_window_minutes: int = 10
    auth_login_max_failures: int = 5
    auth_login_block_minutes: int = 15
    auth_pepper: SecretStr = SecretStr("")
    raw_payload_retention_days: int = 90
    provider_daily_budget_usd: float = 50.0
    provider_monthly_budget_usd: float = 1500.0
    provider_retry_attempts: int = 3
    provider_retry_base_seconds: float = 0.15
    provider_circuit_failure_threshold: int = 10
    provider_circuit_window_size: int = 20
    provider_circuit_failure_rate: float = 0.5
    provider_circuit_cooldown_seconds: int = 300
    provider_emergency_latency_ms: int = 15_000
    provider_benchmark_output_directory: str = "var/provider_benchmarks"
    raw_payload_directory: str = "var/raw_payloads"
    youtube_api_key: str = ""
    youtube_oauth_client_id: str = ""
    youtube_oauth_client_secret: SecretStr = SecretStr("")
    youtube_oauth_redirect_uri: str = "http://localhost:8000/api/v1/oauth/youtube/callback"
    token_encryption_key: SecretStr = SecretStr("")
    discovery_provider_priority: str = "youtube_web,youtube_official"
    metadata_provider_priority: str = "youtube_official"
    comment_provider_priority: str = "youtube_official,youtube_web_comments"
    ingestion_default_query_limit: int = 20
    comment_candidate_limit: int = 12
    comment_sample_limit: int = 100
    comment_refresh_hours: int = 12
    transcript_candidate_limit: int = 8
    transcript_provider_priority: str = "youtube_transcript"
    transcript_preferred_languages: str = "en,en-US,en-GB"
    feature_earlyness_timeline: bool = False
    feature_signal_review_queue: bool = False
    feature_comment_topic_relevance: bool = False
    feature_decision_experience: bool = False
    feature_microtopic_content_gap: bool = False
    feature_feedback_evaluation: bool = False
    feature_topic_snapshot_buckets: bool = False
    feature_channel_profile_feasibility_v2: bool = False
    feature_outcome_suggestions: bool = False
    feature_signal_packaging: bool = False
    feature_youtube_oauth_analytics: bool = False
    feature_query_expansion: bool = False
    feature_ux_today_home_v1: bool = False
    feature_ux_decision_card_v1: bool = False
    feature_ux_simple_scores_v1: bool = False
    feature_ux_simplified_navigation_v1: bool = False
    feature_ux_onboarding_v2: bool = False
    feature_ux_opportunity_detail_v2: bool = False
    feature_ux_brief_v2: bool = False
    feature_ux_results_v2: bool = False
    feature_llm_intelligence: bool = False
    llm_provider: str = "openai"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-5.6-terra"
    openai_auditor_model: str = "gpt-5.6-terra"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_reasoning_effort: str = "low"
    openai_auditor_reasoning_effort: str = "medium"
    openai_request_timeout_seconds: float = 45
    openai_max_output_tokens: int = 4_000
    openai_retry_attempts: int = 2
    llm_max_calls_per_run: int = 24
    llm_max_reconciliations_per_run: int = 4
    llm_max_topic_syntheses_per_run: int = 8
    llm_max_content_gap_syntheses_per_run: int = 6
    llm_max_audits_per_run: int = 12
    llm_daily_token_budget: int = 1_000_000
    llm_reconciliation_daily_token_share: float = 0.12
    llm_topic_synthesis_daily_token_share: float = 0.25
    llm_content_gap_daily_token_share: float = 0.35
    llm_workspace_daily_token_budget: int = 250_000
    llm_require_grounding_audit: bool = True
    llm_circuit_failure_threshold: int = 3
    llm_stale_run_minutes: int = 15
    topic_pipeline_stale_minutes: int = 30
    evaluation_minimum_labels: int = 50

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_web_origins(self) -> list[str]:
        origins = [self.web_origin.rstrip("/")]
        if self.app_env.lower() != "production":
            origins.extend(
                [
                    "http://localhost:3000",
                    "http://127.0.0.1:3000",
                ]
            )
        return list(dict.fromkeys(origins))

    def validate_runtime(self) -> None:
        if self.app_env.lower() != "production":
            return
        errors: list[str] = []
        parsed_origin = urlparse(self.web_origin)
        if parsed_origin.scheme != "https" or not parsed_origin.netloc:
            errors.append("WEB_ORIGIN must be an absolute HTTPS URL")
        if self.demo_mode:
            errors.append("DEMO_MODE must be false")
        if not self.auth_required:
            errors.append("AUTH_REQUIRED must be true")
        if not self.auth_cookie_secure:
            errors.append("AUTH_COOKIE_SECURE must be true")
        if self.auth_password_iterations < 600_000:
            errors.append("AUTH_PASSWORD_ITERATIONS must be at least 600000")
        if not self.auth_pepper.get_secret_value():
            errors.append("AUTH_PEPPER is required")
        if self.feature_llm_intelligence and not self.openai_api_key.get_secret_value():
            errors.append("OPENAI_API_KEY is required when LLM intelligence is enabled")
        if self.feature_youtube_oauth_analytics:
            if not self.youtube_oauth_client_id:
                errors.append("YOUTUBE_OAUTH_CLIENT_ID is required when OAuth analytics is enabled")
            if not self.youtube_oauth_client_secret.get_secret_value():
                errors.append(
                    "YOUTUBE_OAUTH_CLIENT_SECRET is required when OAuth analytics is enabled"
                )
            if not self.token_encryption_key.get_secret_value():
                errors.append("TOKEN_ENCRYPTION_KEY is required when OAuth analytics is enabled")
        if errors:
            raise ValueError("Unsafe production configuration: " + "; ".join(errors))

    @property
    def improvement_features(self) -> ImprovementFeatureFlags:
        return ImprovementFeatureFlags(
            earlyness_timeline=self.feature_earlyness_timeline,
            signal_review_queue=self.feature_signal_review_queue,
            comment_topic_relevance=self.feature_comment_topic_relevance,
            decision_experience=self.feature_decision_experience,
            microtopic_content_gap=self.feature_microtopic_content_gap,
            feedback_evaluation=self.feature_feedback_evaluation,
            topic_snapshot_buckets=self.feature_topic_snapshot_buckets,
            channel_profile_feasibility_v2=self.feature_channel_profile_feasibility_v2,
            outcome_suggestions=self.feature_outcome_suggestions,
            signal_packaging=self.feature_signal_packaging,
            youtube_oauth_analytics=self.feature_youtube_oauth_analytics,
            query_expansion=self.feature_query_expansion,
            ux_today_home_v1=self.feature_ux_today_home_v1,
            ux_decision_card_v1=self.feature_ux_decision_card_v1,
            ux_simple_scores_v1=self.feature_ux_simple_scores_v1,
            ux_simplified_navigation_v1=self.feature_ux_simplified_navigation_v1,
            ux_onboarding_v2=self.feature_ux_onboarding_v2,
            ux_opportunity_detail_v2=self.feature_ux_opportunity_detail_v2,
            ux_brief_v2=self.feature_ux_brief_v2,
            ux_results_v2=self.feature_ux_results_v2,
            llm_intelligence=self.feature_llm_intelligence,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
