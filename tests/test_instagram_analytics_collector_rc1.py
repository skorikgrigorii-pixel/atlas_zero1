from pathlib import Path

import pytest

from az_enterprise.core.instagram_analytics_collector_rc1 import (
    InstagramAnalyticsCollectorRC1,
)


class FakeConnector:

    def __init__(
        self,
        values=None,
    ):
        self.values = values or {}
        self.calls = []

    def _request_json(
        self,
        *,
        method,
        path,
        params,
    ):

        metric = params[
            "metric"
        ]

        self.calls.append(
            metric
        )

        return {
            "data": [
                {
                    "name":
                        metric,
                    "values": [
                        {
                            "value":
                                self.values.get(
                                    metric,
                                    0,
                                )
                        }
                    ],
                }
            ]
        }


def make_collector(
    tmp_path: Path,
    values=None,
):

    connector = FakeConnector(
        values
    )

    collector = InstagramAnalyticsCollectorRC1(
        project_id="franklin",
        root=tmp_path,
        connector=connector,
    )

    return collector, connector


def test_extract_metric_list_value():

    payload = {
        "data": [
            {
                "values": [
                    {
                        "value": 8
                    }
                ]
            }
        ]
    }

    assert (
        InstagramAnalyticsCollectorRC1
        ._extract_metric_value(
            payload
        )
        == 8
    )


def test_collect_media():

    collector, connector = (
        make_collector(
            Path("."),
            {
                "views": 8,
                "likes": 2,
                "total_interactions": 2,
            },
        )
    )

    result = collector.collect_media(
        candidate_id="promo_001",
        media_id="media_001",
    )

    assert result.views == 8
    assert result.likes == 2

    assert (
        result.total_interactions
        == 2
    )

    assert "plays" not in (
        connector.calls
    )

    assert set(
        connector.calls
    ) == set(
        collector.METRICS
    )


def test_unsupported_metric_rejected(
    tmp_path: Path,
):

    collector, _ = make_collector(
        tmp_path
    )

    with pytest.raises(
        ValueError,
        match="Unsupported",
    ):
        collector.collect_metric(
            media_id="x",
            metric="plays",
        )


def test_collect_registered_media(
    tmp_path: Path,
):

    collector, _ = make_collector(
        tmp_path,
        {
            "views": 8,
            "likes": 2,
        },
    )

    path = (
        collector
        .publication_registry_path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        '{"candidate_id":"promo_001",'
        '"media_id":"media_001",'
        '"platform":"instagram",'
        '"status":"PUBLISHED"}\n',
        encoding="utf-8",
    )

    results = (
        collector
        .collect_registered_media()
    )

    assert len(results) == 1

    assert (
        results[0].candidate_id
        == "promo_001"
    )

    assert (
        collector
        .analytics_registry_path
        .is_file()
    )


def test_nonpublished_ignored(
    tmp_path: Path,
):

    collector, connector = (
        make_collector(
            tmp_path
        )
    )

    path = (
        collector
        .publication_registry_path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        '{"candidate_id":"promo_001",'
        '"media_id":"media_001",'
        '"platform":"instagram",'
        '"status":"FAILED"}\n',
        encoding="utf-8",
    )

    results = (
        collector
        .collect_registered_media()
    )

    assert results == []
    assert connector.calls == []
