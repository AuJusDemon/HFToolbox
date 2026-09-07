"""Pure activity grouping for bounded bump reports."""


def quiet_groups(periods: list[dict]) -> list[dict]:
    result: list[dict] = []
    quiet: list[dict] = []

    def flush():
        nonlocal quiet
        if not quiet:
            return
        newest, oldest = quiet[0], quiet[-1]
        result.append({
            "kind": "quiet_group",
            "count": len(quiet),
            "start_ts": oldest.get("bump_ts"),
            "end_ts": newest.get("end_ts") or newest.get("bump_ts"),
            "summary": "No replies or contract activity",
        })
        quiet = []

    for period in periods:
        is_quiet = (
            not period.get("is_open")
            and not period.get("period_replies")
            and not period.get("contracts_opened")
            and not period.get("contracts_completed")
            and not period.get("period_skips")
        )
        if is_quiet:
            quiet.append(period)
            continue
        flush()
        result.append({"kind": "period", **period})
    flush()
    return result
