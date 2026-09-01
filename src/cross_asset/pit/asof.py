"""Point-in-time selection helpers."""


def filter_asof(observations, decision_time):
    """Filter iterable/dicts or DataFrame-like observations by available_at."""
    if hasattr(observations, "loc"):
        return observations.loc[observations["available_at"] <= decision_time].copy()
    return [x for x in observations if x.get("available_at") <= decision_time]


def query_asof(connection, decision_time, series_id=None, latest=True):
    from cross_asset.storage.queries import latest_observations_asof, observations_asof

    return (latest_observations_asof if latest else observations_asof)(
        connection, decision_time, series_id
    )


asof_query = query_asof
