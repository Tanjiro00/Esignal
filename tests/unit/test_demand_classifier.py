from packages.demand import classify_comment


def test_comment_taxonomy_distinguishes_actionable_demand_from_praise() -> None:
    tutorial = classify_comment(
        "Please make a step by step tutorial for running this on a private repository?"
    )
    praise = classify_comment("Amazing video, thank you!")

    assert tutorial.taxonomy == "request_for_tutorial"
    assert tutorial.demand_probability >= 0.8
    assert tutorial.spam_probability < 0.1
    assert praise.taxonomy == "generic_praise"
    assert praise.demand_probability < 0.2


def test_comment_classifier_penalizes_promotional_spam() -> None:
    spam = classify_comment("Subscribe to my channel and join telegram https://spam.example")

    assert spam.taxonomy == "spam_irrelevant"
    assert spam.spam_probability >= 0.8
    assert spam.demand_probability == 0
    assert len(spam.embedding) == 64


def test_comment_classifier_rejects_summary_bots_and_non_request_praise() -> None:
    summary_bot = classify_comment(
        "Here's quick summary, so you know if it's worth watching. "
        "If you want keypoints and notes, just like the comment."
    )
    praise = classify_comment(
        "This real-world guide explained the workflow clearly and was extremely useful."
    )

    assert summary_bot.taxonomy == "spam_irrelevant"
    assert summary_bot.demand_probability == 0
    assert praise.taxonomy != "test_or_proof_request"


def test_creator_production_question_is_not_trend_demand() -> None:
    question = classify_comment("I love your editing style! Would you share who edits your videos?")

    assert question.taxonomy == "emotional_reaction"
    assert question.demand_probability < 0.2
