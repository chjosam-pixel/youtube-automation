"""YouTube Analytics report — pulls channel performance metrics via the
YouTube Analytics API and prints a structured CTO-style dashboard."""

import json
from datetime import date, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from pipeline.config import YOUTUBE_CLIENT_SECRET_FILE, YOUTUBE_TOKEN_FILE

# Analytics needs an extra scope beyond the upload-only token.
# On first run with this scope the user must re-authorize once locally.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]

ANALYTICS_TOKEN_FILE = YOUTUBE_TOKEN_FILE.parent / "token_analytics.json"


def _get_auth():
    creds = None
    if ANALYTICS_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(ANALYTICS_TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(YOUTUBE_CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        ANALYTICS_TOKEN_FILE.write_text(creds.to_json())
    return creds


def _youtube_client(creds):
    return build("youtube", "v3", credentials=creds)


def _analytics_client(creds):
    return build("youtubeAnalytics", "v2", credentials=creds)


def _get_channel_id(yt):
    resp = yt.channels().list(part="id,snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel found for this account.")
    ch = items[0]
    return ch["id"], ch["snippet"]["title"]


def _analytics_query(analytics, channel_id: str, start: str, end: str, metrics: str, dimensions: str = "", filters: str = ""):
    params = dict(
        ids=f"channel=={channel_id}",
        startDate=start,
        endDate=end,
        metrics=metrics,
    )
    if dimensions:
        params["dimensions"] = dimensions
    if filters:
        params["filters"] = filters
    return analytics.reports().query(**params).execute()


def _fmt(val, kind="int"):
    if val is None:
        return "–"
    if kind == "pct":
        return f"{val:.1f}%"
    if kind == "sec":
        m, s = divmod(int(val), 60)
        return f"{m}분 {s:02d}초"
    if kind == "float":
        return f"{val:.2f}"
    return f"{int(val):,}"


def _retention_bar(ratio: float, width: int = 20) -> str:
    filled = round(ratio * width)
    return "█" * filled + "░" * (width - filled)


def run_report(days: int = 7) -> str:
    creds = _get_auth()
    yt = _youtube_client(creds)
    analytics = _analytics_client(creds)

    channel_id, channel_name = _get_channel_id(yt)
    end = date.today() - timedelta(days=1)   # yesterday (API lag)
    start = end - timedelta(days=days - 1)
    start_str, end_str = start.isoformat(), end.isoformat()

    # ── Overall channel metrics ──────────────────────────────────────────────
    overall = _analytics_query(
        analytics, channel_id, start_str, end_str,
        "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
        "likes,comments,subscribersGained,subscribersLost,"
        "annotationClickThroughRate,cardClickRate",
    )
    row = overall.get("rows", [[None] * 10])[0]
    (views, est_min, avg_sec, avg_pct,
     likes, comments, subs_gained, subs_lost,
     ann_ctr, card_ctr) = row

    net_subs = (subs_gained or 0) - (subs_lost or 0)

    # ── Top 5 videos by views ────────────────────────────────────────────────
    top_videos_resp = _analytics_query(
        analytics, channel_id, start_str, end_str,
        "views,averageViewDuration,averageViewPercentage,likes,comments",
        dimensions="video",
    )
    top_rows = sorted(
        top_videos_resp.get("rows", []),
        key=lambda r: r[1], reverse=True
    )[:5]

    # Fetch video titles
    video_ids = [r[0] for r in top_rows]
    titles = {}
    if video_ids:
        vresp = yt.videos().list(
            part="snippet", id=",".join(video_ids)
        ).execute()
        for item in vresp.get("items", []):
            titles[item["id"]] = item["snippet"]["title"]

    # ── Retention curve (audience-retention at fixed checkpoints) ───────────
    # YouTube Analytics audience retention requires a specific video filter;
    # we pull the top video's elapsedVideoTimeRatio vs audienceWatchRatio.
    retention_lines = []
    if video_ids:
        top_vid = video_ids[0]
        try:
            ret_resp = _analytics_query(
                analytics, channel_id, start_str, end_str,
                "audienceWatchRatio,relativeRetentionPerformance",
                dimensions="elapsedVideoTimeRatio",
                filters=f"video=={top_vid}",
            )
            ret_rows = ret_resp.get("rows", [])
            # Sample 10 evenly spaced points
            if ret_rows:
                step = max(1, len(ret_rows) // 10)
                sampled = ret_rows[::step][:10]
                retention_lines.append(f"\n  ▶ 상위 영상 시청 유지율: {titles.get(top_vid, top_vid)[:40]}")
                for r_row in sampled:
                    pct_pos = int(r_row[0] * 100)
                    ratio = r_row[1] if r_row[1] is not None else 0.0
                    bar = _retention_bar(ratio)
                    retention_lines.append(f"    {pct_pos:3d}% │ {bar} {ratio*100:.0f}%")
        except Exception as exc:
            retention_lines.append(f"  (유지율 데이터 없음: {exc})")

    # ── Traffic sources ──────────────────────────────────────────────────────
    traffic_resp = _analytics_query(
        analytics, channel_id, start_str, end_str,
        "views",
        dimensions="insightTrafficSourceType",
    )
    traffic_rows = sorted(
        traffic_resp.get("rows", []),
        key=lambda r: r[1], reverse=True
    )[:5]
    total_traffic_views = sum(r[1] for r in traffic_rows) or 1

    # ── Shorts vs Long-form split ────────────────────────────────────────────
    device_resp = _analytics_query(
        analytics, channel_id, start_str, end_str,
        "views,estimatedMinutesWatched",
        dimensions="deviceType",
    )
    device_rows = device_resp.get("rows", [])

    # ── Build report string ──────────────────────────────────────────────────
    lines = [
        "━" * 54,
        f"  📊 채널 성과 리포트 — {channel_name}",
        f"  기간: {start_str} ~ {end_str} ({days}일)",
        "━" * 54,
        "",
        "【 전체 채널 지표 】",
        f"  조회수              {_fmt(views)}",
        f"  총 시청 시간        {_fmt(est_min)} 분",
        f"  평균 시청 지속시간  {_fmt(avg_sec, 'sec')}",
        f"  평균 시청률         {_fmt(avg_pct, 'pct')}",
        f"  좋아요              {_fmt(likes)}",
        f"  댓글                {_fmt(comments)}",
        f"  구독자 순증가       {'+' if net_subs >= 0 else ''}{_fmt(net_subs)}",
        f"    (획득 {_fmt(subs_gained)} / 이탈 {_fmt(subs_lost)})",
        f"  카드 클릭률         {_fmt(card_ctr, 'pct')}",
        "",
        "【 시청 유지율 】",
    ]
    lines += retention_lines or ["  (데이터 없음)"]

    lines += [
        "",
        "【 인기 영상 TOP 5 (조회수 기준) 】",
    ]
    for i, r_row in enumerate(top_rows, 1):
        vid, v_views, v_avg_sec, v_avg_pct, v_likes, v_comments = r_row
        title = titles.get(vid, vid)[:42]
        lines.append(f"  {i}. {title}")
        lines.append(
            f"     조회 {_fmt(v_views)} | 평균시청 {_fmt(v_avg_sec,'sec')} "
            f"({_fmt(v_avg_pct,'pct')}) | 👍{_fmt(v_likes)} 💬{_fmt(v_comments)}"
        )

    lines += [
        "",
        "【 유입 경로 TOP 5 】",
    ]
    source_labels = {
        "YT_SEARCH": "유튜브 검색",
        "SUGGESTED_VIDEOS": "추천 영상",
        "BROWSE_FEATURES": "홈/탐색",
        "EXTERNAL": "외부 링크",
        "NO_LINK_EMBEDDED": "임베드",
        "SHORTS": "쇼츠 피드",
        "NOTIFICATION": "알림",
        "PLAYLIST": "재생목록",
    }
    for src, src_views in traffic_rows:
        share = src_views / total_traffic_views * 100
        label = source_labels.get(src, src)
        lines.append(f"  {label:<14} {_fmt(src_views):>7} 회  ({share:.0f}%)")

    lines += [
        "",
        "【 기기별 시청 】",
    ]
    device_labels = {
        "MOBILE": "모바일",
        "DESKTOP": "데스크톱",
        "TABLET": "태블릿",
        "TV": "TV",
        "GAME_CONSOLE": "게임기",
    }
    for dev_row in sorted(device_rows, key=lambda r: r[1], reverse=True):
        dev, dev_views, dev_min = dev_row
        lines.append(f"  {device_labels.get(dev, dev):<10} {_fmt(dev_views):>7} 회")

    lines += ["", "━" * 54]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    print(run_report(days=days))
