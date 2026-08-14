from packages.provider_benchmark import ProviderBenchmarkService


def test_default_benchmark_fixture_expands_to_one_hundred_queries() -> None:
    fixture = ProviderBenchmarkService.load_fixture()
    queries = ProviderBenchmarkService.expand_queries(fixture)

    assert len(queries) == 100
    assert len(set(queries)) == 100
    assert fixture["corpus_targets"]["videos"] == 100
    assert fixture["corpus_targets"]["videos_with_captions"] == 30
