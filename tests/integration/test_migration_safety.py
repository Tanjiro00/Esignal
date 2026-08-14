from alembic import command
from alembic.config import Config
from sqlalchemy import BigInteger, String, create_engine, inspect, text

from apps.api.config import get_settings


def test_clean_sqlite_database_upgrades_to_head(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "migration-safety.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    try:
        command.upgrade(Config("alembic.ini"), "head")
        engine = create_engine(database_url)
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version")) == "a7d9e2f4b6c8"
            )

        schema = inspect(engine)
        channel_columns = {
            column["name"]: column for column in schema.get_columns("youtube_channels")
        }
        signal_columns = {column["name"]: column for column in schema.get_columns("signals")}
        assert isinstance(channel_columns["view_count"]["type"], BigInteger)
        assert isinstance(signal_columns["evidence_version"]["type"], String)
        assert signal_columns["evidence_version"]["type"].length == 120
        assert "topic_lifecycle_transitions" in schema.get_table_names()
        assert "topic_lifecycle_summaries" in schema.get_table_names()
        assert "topic_video_observations" in schema.get_table_names()
        assert "first_observation_quality" in {
            column["name"] for column in schema.get_columns("topic_video_observations")
        }
        assert "signal_reviews" in schema.get_table_names()
        assert "signal_review_events" in schema.get_table_names()
        assert "comment_topic_relevance" in schema.get_table_names()
        assert "comment_topic_relevance_events" in schema.get_table_names()
        assert "topic_content_patterns" in schema.get_table_names()
        assert "topic_content_gaps" in schema.get_table_names()
        assert "evaluation_labels" in schema.get_table_names()
        assert "topic_snapshot_buckets" in schema.get_table_names()
        assert "outcome_suggestions" in schema.get_table_names()
        assert "signal_packaging" in schema.get_table_names()
        assert "youtube_oauth_connections" in schema.get_table_names()
        assert "youtube_oauth_states" in schema.get_table_names()
        assert "youtube_owned_analytics" in schema.get_table_names()
        assert "youtube_oauth_audit_events" in schema.get_table_names()
        assert "query_suggestions" in schema.get_table_names()
        assert "llm_intelligence_runs" in schema.get_table_names()
        assert "workspace_discovery_queries" in schema.get_table_names()
        assert "user_credentials" in schema.get_table_names()
        assert "user_sessions" in schema.get_table_names()
        assert "auth_login_attempts" in schema.get_table_names()
        assert "raw_api_snapshots" in schema.get_table_names()
        assert "derived_metric_points" in schema.get_table_names()
        assert "backtest_runs" in schema.get_table_names()
        assert "backtest_checkpoints" in schema.get_table_names()
        assert "backtest_predictions" in schema.get_table_names()
        assert "backtest_outcomes" in schema.get_table_names()
        assert "backtest_reports" in schema.get_table_names()
        assert "is_platform_admin" in {column["name"] for column in schema.get_columns("users")}
        assert "synthesis_json" in signal_columns
        backtest_run_columns = {
            column["name"]: column for column in schema.get_columns("backtest_runs")
        }
        backtest_checkpoint_columns = {
            column["name"]: column for column in schema.get_columns("backtest_checkpoints")
        }
        backtest_prediction_columns = {
            column["name"]: column for column in schema.get_columns("backtest_predictions")
        }
        backtest_outcome_columns = {
            column["name"]: column for column in schema.get_columns("backtest_outcomes")
        }
        backtest_report_columns = {
            column["name"]: column for column in schema.get_columns("backtest_reports")
        }
        assert {
            "idempotency_key",
            "status",
            "source_kind",
            "dataset_version",
            "code_revision",
            "code_dirty",
            "migration_revision",
            "config_json",
            "model_versions_json",
        }.issubset(backtest_run_columns)
        assert {
            "run_id",
            "checkpoint_at",
            "status",
            "manifest_version",
            "manifest_json",
            "input_hash",
            "eligible_video_count",
            "snapshot_count",
            "prediction_count",
        }.issubset(backtest_checkpoint_columns)
        assert {
            "checkpoint_id",
            "candidate_key",
            "rank",
            "score",
            "algorithm_version",
            "evidence_json",
            "evidence_hash",
        }.issubset(backtest_prediction_columns)
        assert {
            "checkpoint_id",
            "candidate_key",
            "status",
            "fired",
            "label_method",
            "supply_growth_ratio",
            "peak_lift",
            "fired_at",
            "horizon_end",
            "evaluation_as_of",
            "evidence_json",
            "evidence_hash",
        }.issubset(backtest_outcome_columns)
        assert {
            "idempotency_key",
            "report_version",
            "algorithm_version",
            "label_version",
            "status",
            "checkpoint_ids_json",
            "metrics_json",
            "gate_json",
            "markdown_report",
            "content_hash",
        }.issubset(backtest_report_columns)
        llm_run_columns = {
            column["name"]: column for column in schema.get_columns("llm_intelligence_runs")
        }

        assert {
            "backtest_cohorts",
            "backtest_cohort_checkpoints",
        }.issubset(schema.get_table_names())
        assert "ix_topic_snapshots_observed_topic" in {
            index["name"] for index in schema.get_indexes("topic_snapshots")
        }
        assert {
            "cohort_id",
            "checkpoint_id",
            "ordinal",
            "split",
            "checkpoint_at",
            "horizon_end",
            "outcome_ready_at",
            "coverage_json",
            "frozen_at",
        } == {column["name"] for column in schema.get_columns("backtest_cohort_checkpoints")}
        assert {
            "task",
            "scope_kind",
            "scope_id",
            "input_hash",
            "provider",
            "model",
            "prompt_version",
            "status",
            "evidence_refs_json",
            "output_json",
            "validation_json",
            "usage_json",
            "provider_response_id",
            "latency_ms",
            "error_code",
            "error_message",
        }.issubset(llm_run_columns)
        pipeline_run_columns = {
            column["name"]: column for column in schema.get_columns("topic_pipeline_runs")
        }
        assert {
            "llm_policy_version",
            "llm_trace_json",
        }.issubset(pipeline_run_columns)
        transition_columns = {
            column["name"]: column for column in schema.get_columns("topic_lifecycle_transitions")
        }
        summary_columns = {
            column["name"]: column for column in schema.get_columns("topic_lifecycle_summaries")
        }
        assert {
            "topic_id",
            "from_stage",
            "to_stage",
            "transitioned_at",
            "measurement_id",
            "score",
            "reason_codes_json",
            "history_version",
        }.issubset(transition_columns)
        assert {
            "first_discovered_at",
            "first_signal_visible_at",
            "first_breakout_at",
            "first_large_channel_adoption_at",
            "latest_measurement_at",
            "evidence_json",
            "backfill_version",
        }.issubset(summary_columns)
        review_columns = {column["name"]: column for column in schema.get_columns("signal_reviews")}
        review_event_columns = {
            column["name"]: column for column in schema.get_columns("signal_review_events")
        }
        assert {
            "workspace_id",
            "signal_id",
            "status",
            "reviewer_id",
            "reason_codes_json",
            "thesis_override",
            "opportunity_override_json",
            "evidence_selection_json",
            "submitted_at",
            "review_version",
        }.issubset(review_columns)
        assert {
            "review_id",
            "workspace_id",
            "signal_id",
            "event_type",
            "from_status",
            "to_status",
            "reason_codes_json",
            "changes_json",
            "provenance_json",
            "idempotency_key",
        }.issubset(review_event_columns)
        relevance_columns = {
            column["name"]: column for column in schema.get_columns("comment_topic_relevance")
        }
        relevance_event_columns = {
            column["name"]: column
            for column in schema.get_columns("comment_topic_relevance_events")
        }
        assert {
            "comment_id",
            "topic_id",
            "video_id",
            "is_relevant",
            "relevance_score",
            "comment_topic_semantic_similarity",
            "comment_video_semantic_similarity",
            "entity_overlap_score",
            "claim_support_score",
            "intent_actionability_score",
            "duplicate_or_echo_probability",
            "override_decision",
            "model_version",
            "input_hash",
        }.issubset(relevance_columns)
        assert {
            "relevance_id",
            "topic_id",
            "comment_id",
            "event_type",
            "previous_result_json",
            "result_json",
            "actor_id",
            "idempotency_key",
            "model_version",
        }.issubset(relevance_event_columns)
        demand_cluster_columns = {
            column["name"]: column for column in schema.get_columns("demand_clusters")
        }
        assert {
            "visibility_status",
            "evidence_strength",
            "median_relevance_score",
            "high_actionability_count",
            "relevance_model_version",
        }.issubset(demand_cluster_columns)
        topic_columns = {column["name"]: column for column in schema.get_columns("topics")}
        assert {
            "identity_json",
            "specificity_score",
            "thesis_support_ratio",
            "visibility_reason_codes_json",
        }.issubset(topic_columns)
        content_pattern_columns = {
            column["name"]: column for column in schema.get_columns("topic_content_patterns")
        }
        assert {
            "topic_id",
            "video_id",
            "pattern_key",
            "pattern_json",
            "evidence_json",
            "model_version",
            "calculated_at",
        }.issubset(content_pattern_columns)
        content_gap_columns = {
            column["name"]: column for column in schema.get_columns("topic_content_gaps")
        }
        assert {
            "workspace_id",
            "topic_id",
            "gap_key",
            "rank",
            "status",
            "occupied_pattern_json",
            "open_gap_json",
            "score_components_json",
            "evidence_json",
            "model_version",
            "ranking_version",
            "calculated_at",
        }.issubset(content_gap_columns)
        signal_action_columns = {
            column["name"]: column for column in schema.get_columns("signal_actions")
        }
        assert {
            "comment",
            "opportunity_id",
            "feedback_version",
        }.issubset(signal_action_columns)
        evaluation_columns = {
            column["name"]: column for column in schema.get_columns("evaluation_labels")
        }
        assert {
            "topic_id",
            "signal_id",
            "reviewer_id",
            "as_of",
            "label",
            "additional_labels_json",
            "evidence_snapshot_json",
            "notes",
            "model_versions_json",
            "label_version",
        }.issubset(evaluation_columns)
        bucket_columns = {
            column["name"]: column for column in schema.get_columns("topic_snapshot_buckets")
        }
        assert {
            "topic_id",
            "resolution",
            "bucket_start",
            "bucket_end",
            "first_json",
            "last_json",
            "min_json",
            "max_json",
            "avg_json",
            "source_measurement_ids_json",
            "bucket_version",
        }.issubset(bucket_columns)
        channel_profile_columns = {
            column["name"]: column for column in schema.get_columns("channel_profiles")
        }
        assert {
            "core_topics_json",
            "adjacent_topics_json",
            "legacy_topics_json",
            "successful_formats_json",
            "upload_cadence_json",
            "audience_sophistication",
            "creator_authority",
            "risk_tolerance",
            "team_size",
            "research_capacity_hours",
            "filming_required",
            "external_guests_required",
            "editing_complexity",
            "access_to_products_json",
            "experiment_level",
            "evergreen_trend_balance",
            "weekday_publish_only",
            "content_calendar_json",
            "inference_json",
            "explicit_overrides_json",
            "profile_version",
        }.issubset(channel_profile_columns)
        outcome_columns = {
            column["name"]: column for column in schema.get_columns("published_outcomes")
        }
        assert {
            "link_status",
            "association_version",
            "metrics_version",
            "updated_at",
        }.issubset(outcome_columns)
        suggestion_columns = {
            column["name"]: column for column in schema.get_columns("outcome_suggestions")
        }
        assert {
            "workspace_id",
            "video_id",
            "signal_id",
            "suggested_brief_id",
            "selected_brief_id",
            "outcome_id",
            "status",
            "match_confidence",
            "reason_codes_json",
            "match_features_json",
            "baseline_json",
            "metrics_json",
            "model_version",
        }.issubset(suggestion_columns)
        packaging_columns = {
            column["name"]: column for column in schema.get_columns("signal_packaging")
        }
        assert {
            "workspace_id",
            "signal_id",
            "opportunity_id",
            "content_brief_id",
            "packaging_json",
            "evidence_ids_json",
            "regeneration_counts_json",
            "packaging_version",
        }.issubset(packaging_columns)
        oauth_columns = {
            column["name"]: column for column in schema.get_columns("youtube_oauth_connections")
        }
        assert {
            "workspace_id",
            "channel_id",
            "status",
            "scopes_json",
            "encrypted_access_token",
            "encrypted_refresh_token",
            "token_expires_at",
            "verified_at",
            "last_synced_at",
            "last_refresh_error",
        }.issubset(oauth_columns)
        analytics_columns = {
            column["name"]: column for column in schema.get_columns("youtube_owned_analytics")
        }
        assert {
            "workspace_id",
            "channel_id",
            "video_id",
            "youtube_video_id",
            "views",
            "watch_time_minutes",
            "average_view_duration_seconds",
            "average_percentage_viewed",
            "subscribers_gained",
            "revenue",
            "traffic_source_groups_json",
            "geography_json",
            "content_type",
            "published_at",
            "duration_seconds",
            "analytics_version",
        }.issubset(analytics_columns)
        discovery_query_columns = {
            column["name"]: column for column in schema.get_columns("discovery_queries")
        }
        assert {
            "precision_score",
            "precision_sample_size",
            "quality_status",
            "last_precision_at",
        }.issubset(discovery_query_columns)
        query_suggestion_columns = {
            column["name"]: column for column in schema.get_columns("query_suggestions")
        }
        assert {
            "query",
            "normalized_query",
            "status",
            "source_type",
            "source_entity",
            "source_topic_id",
            "source_evidence_ids_json",
            "rationale",
            "anchor_terms_json",
            "quality_reason_codes_json",
            "broadness_score",
            "precision_score",
            "precision_sample_size",
            "discovery_query_id",
            "reviewed_by",
            "reviewed_at",
            "model_version",
        }.issubset(query_suggestion_columns)
    finally:
        get_settings.cache_clear()
