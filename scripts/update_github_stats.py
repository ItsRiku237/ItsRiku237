import os
import re
import json
import urllib.request
from datetime import date, timedelta


USERNAME = os.environ.get("GITHUB_USERNAME", "ItsRiku237")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

START_DATE = date(2025, 10, 4)
TODAY = date.today()


GRAPHQL = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def github_graphql(query, variables):
    payload = json.dumps({
        "query": query,
        "variables": variables
    }).encode("utf-8")

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-stats"
        }
    )

    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def get_contribution_days_graphql():
    days_map = {}
    current_start = START_DATE

    while current_start <= TODAY:
        current_end = min(current_start + timedelta(days=364), TODAY)

        variables = {
            "login": USERNAME,
            "from": f"{current_start.isoformat()}T00:00:00Z",
            "to": f"{current_end.isoformat()}T23:59:59Z"
        }

        result = github_graphql(GRAPHQL, variables)

        if "errors" in result:
            raise RuntimeError(json.dumps(result["errors"], indent=2))

        calendar = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]

        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                day_date = date.fromisoformat(day["date"])
                if START_DATE <= day_date <= TODAY:
                    days_map[day_date] = day["contributionCount"]

        current_start = current_end + timedelta(days=1)

    days = []
    cursor = START_DATE
    while cursor <= TODAY:
        days.append({
            "date": cursor,
            "count": days_map.get(cursor, 0)
        })
        cursor += timedelta(days=1)

    return days


def get_contribution_days_public():
    url = f"https://github.com/users/{USERNAME}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")

    days_map = {}
    for m in re.finditer(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*id="([^"]*)"', html):
        d_str = m.group(1)
        d_id = m.group(2)
        tip_match = re.search(rf'<tool-tip\b[^>]*\bfor="{d_id}"[^>]*>(.*?)</tool-tip>', html, re.DOTALL)
        if tip_match:
            tip_text = tip_match.group(1).strip()
            count_match = re.search(r'(\d+)\s+contribution', tip_text)
            count = int(count_match.group(1)) if count_match else 0
        else:
            count = 0
        d_val = date.fromisoformat(d_str)
        if START_DATE <= d_val <= TODAY:
            days_map[d_val] = count

    days = []
    cursor = START_DATE
    while cursor <= TODAY:
        days.append({
            "date": cursor,
            "count": days_map.get(cursor, 0)
        })
        cursor += timedelta(days=1)

    return days


def get_contribution_days():
    if TOKEN:
        try:
            return get_contribution_days_graphql()
        except Exception as err:
            print(f"GraphQL failed ({err}), falling back to public contributions scrape...")
            return get_contribution_days_public()
    else:
        return get_contribution_days_public()


def calculate_stats(days):
    contribution_map = {
        item["date"]: item["count"]
        for item in days
    }

    total = sum(item["count"] for item in days)

    # Find the most recent date with contributions
    last_active_date = None
    for item in reversed(days):
        if item["count"] > 0:
            last_active_date = item["date"]
            break

    # -----------------------------------------
    # CURRENT STREAK
    # -----------------------------------------
    current_streak = 0
    streak_end = None
    streak_start = None

    cursor = TODAY

    # If today has no contribution, start checking from yesterday.
    if contribution_map.get(cursor, 0) == 0:
        cursor -= timedelta(days=1)

    while contribution_map.get(cursor, 0) > 0:
        if streak_end is None:
            streak_end = cursor
        streak_start = cursor
        current_streak += 1
        cursor -= timedelta(days=1)

    is_active = current_streak > 0

    if current_streak == 0:
        if last_active_date:
            current_streak_range = f"LAST ACTIVE → {last_active_date.strftime('%b %d')}"
            current_streak_date = last_active_date.strftime("%b %d")
        else:
            current_streak_range = "NO RECENT ACTIVITY"
            current_streak_date = "—"
    elif current_streak == 1:
        current_streak_range = f"ACTIVE → {streak_end.strftime('%b %d')}"
        current_streak_date = streak_end.strftime("%b %d")
    else:
        current_streak_range = f"{streak_start.strftime('%b %d')} → {streak_end.strftime('%b %d')}"
        current_streak_date = streak_end.strftime("%b %d")

    # -----------------------------------------
    # LONGEST STREAK
    # -----------------------------------------
    longest_streak = 0
    longest_start = None
    longest_end = None

    running = 0
    running_start = None

    for item in days:
        if item["count"] > 0:
            if running == 0:
                running_start = item["date"]
            running += 1

            if running > longest_streak:
                longest_streak = running
                longest_start = running_start
                longest_end = item["date"]
        else:
            running = 0
            running_start = None

    return {
        "total": total,
        "current_streak": current_streak,
        "is_active": is_active,
        "current_streak_range": current_streak_range,
        "current_streak_date": current_streak_date,
        "longest_streak": longest_streak,
        "longest_from": (
            longest_start.strftime("%b %d")
            if longest_start else "—"
        ),
        "longest_to": (
            longest_end.strftime("%b %d")
            if longest_end else "—"
        ),
        "today": TODAY.strftime("%b %d, %Y"),
        "from_date": START_DATE.strftime("%b %d, %Y")
    }


def update_svg(stats):
    svg_files = [
        {"filename": "github-stats.svg", "is_dark": True},
        {"filename": "github-stats-light.svg", "is_dark": False}
    ]

    for cfg in svg_files:
        filename = cfg["filename"]
        is_dark = cfg["is_dark"]
        template_path = os.path.join("templates", filename)
        output_path = os.path.join("assets", filename)

        # Preserve verified total contributions if running locally without token
        total_to_display = stats["total"]
        if not TOKEN and os.path.exists(output_path):
            with open(output_path, "r", encoding="utf-8") as f:
                existing_svg = f.read()
            prev_match = re.search(r'<!-- BOX 1 — TOTAL CONTRIBUTIONS -->[\s\S]*?<!-- NUMBER -->[\s\S]*?<text[^>]*>\s*(\d+)', existing_svg)
            if prev_match:
                prev_total = int(prev_match.group(1))
                if prev_total > total_to_display:
                    total_to_display = prev_total

        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as file:
                svg = file.read()
        else:
            with open(output_path, "r", encoding="utf-8") as file:
                svg = file.read()

        dot_color = (
            ("#e7b45a" if is_dark else "#a86e10")
            if stats["is_active"]
            else ("#77746e" if is_dark else "#9b978f")
        )
        badge_text = "STREAK" if stats["is_active"] else "REST"
        badge_fill = ("#241e12" if is_dark else "#faebd0") if stats["is_active"] else ("#16191c" if is_dark else "#e5e2da")
        badge_stroke = ("#4a3b1d" if is_dark else "#e0cfa8") if stats["is_active"] else ("#2d3339" if is_dark else "#cfcac0")
        badge_color = ("#e7b45a" if is_dark else "#a86e10") if stats["is_active"] else ("#8f8c85" if is_dark else "#77736c")
        ring_dash = "100 15" if stats["is_active"] else "0 130"
        flame_glow_opacity = ".25" if stats["is_active"] else "0"
        flame_body_opacity = "1" if stats["is_active"] else ".3"

        replacements = {
            "{{TOTAL_CONTRIBUTIONS}}": str(total_to_display),
            "{{CURRENT_STREAK}}": str(stats["current_streak"]),
            "{{CURRENT_STREAK_RANGE}}": stats["current_streak_range"],
            "{{CURRENT_STREAK_DOT_COLOR}}": dot_color,
            "{{CURRENT_STREAK_BADGE}}": badge_text,
            "{{CURRENT_STREAK_BADGE_FILL}}": badge_fill,
            "{{CURRENT_STREAK_BADGE_STROKE}}": badge_stroke,
            "{{CURRENT_STREAK_BADGE_COLOR}}": badge_color,
            "{{CURRENT_STREAK_RING_DASH}}": ring_dash,
            "{{CURRENT_STREAK_GLOW_OPACITY}}": flame_glow_opacity,
            "{{CURRENT_STREAK_FLAME_OPACITY}}": flame_body_opacity,
            "{{LONGEST_STREAK}}": str(stats["longest_streak"]),
            "{{CURRENT_STREAK_DATE}}": stats["current_streak_date"],
            "{{LONGEST_FROM}}": stats["longest_from"],
            "{{LONGEST_TO}}": stats["longest_to"],
            "{{TODAY}}": stats["today"],
            "{{TOTAL_FROM}}": stats["from_date"]
        }

        for old, new in replacements.items():
            svg = svg.replace(old, new)

        # Fallback regex in case placeholders were already replaced in output_path
        # BOX 1: NUMBER
        svg = re.sub(
            r'(<!-- BOX 1 — TOTAL CONTRIBUTIONS -->[\s\S]*?<!-- NUMBER -->[\s\S]*?<text[^>]*>\s*)(?:\{\{TOTAL_CONTRIBUTIONS\}\}|\d+)(\s*</text>)',
            r'\g<1>' + str(total_to_display) + r'\2',
            svg
        )
        # BOX 1: RANGE
        svg = re.sub(
            r'(<!-- BOX 1 — TOTAL CONTRIBUTIONS -->[\s\S]*?<!-- RANGE -->[\s\S]*?<text[^>]*>\s*)[^<\n]+?(\s*</text>)',
            r'\g<1>' + f'{stats["from_date"]} → {stats["today"]}' + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 1 — TOTAL CONTRIBUTIONS -->[\s\S]*?<text x="25"\s+y="94"[^>]*>\s*)[^<\n]+?(\s*</text>)',
            r'\g<1>' + f'{stats["from_date"]} → {stats["today"]}' + r'\2',
            svg
        )

        # BOX 2: NUMBER
        svg = re.sub(
            r'(<!-- BOX 2 — CURRENT STREAK -->[\s\S]*?<!-- NUMBER -->[\s\S]*?<text[^>]*>\s*)(?:\{\{CURRENT_STREAK\}\}|\d+)(\s*</text>)',
            r'\g<1>' + str(stats["current_streak"]) + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 2 — CURRENT STREAK -->[\s\S]*?<g transform="translate\(485 69\)"[\s\S]*?<text[^>]*>\s*)(?:\{\{CURRENT_STREAK\}\}|\d+)(\s*</text>)',
            r'\g<1>' + str(stats["current_streak"]) + r'\2',
            svg
        )

        # BOX 2: RANGE
        svg = re.sub(
            r'(<!-- BOX 2 — CURRENT STREAK -->[\s\S]*?<!-- RANGE -->[\s\S]*?<text[^>]*>\s*)[^<\n]+?(\s*</text>)',
            r'\g<1>' + stats["current_streak_range"] + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 2 — CURRENT STREAK -->[\s\S]*?<text x="374"\s+y="94"[^>]*>\s*)[^<\n]+?(\s*</text>)',
            r'\g<1>' + stats["current_streak_range"] + r'\2',
            svg
        )
        # BOX 2: DOT COLOR
        svg = re.sub(
            r'(<!-- BOX 2 — CURRENT STREAK -->[\s\S]*?<!-- RANGE -->[\s\S]*?<circle[^>]*\bfill=")[^"]*(")',
            r'\g<1>' + dot_color + r'\2',
            svg
        )

        # BOX 2: BADGE
        svg = re.sub(
            r'(<!-- Streak badge -->[\s\S]*?<rect\b[^>]*\bfill=")[^"]*("[\s\S]*?\bstroke=")[^"]*(")',
            r'\g<1>' + badge_fill + r'\2' + badge_stroke + r'\3',
            svg
        )
        svg = re.sub(
            r'(<!-- Streak badge -->[\s\S]*?<text\b[^>]*\bfill=")[^"]*("[\s\S]*?>\s*)(?:STREAK|REST|INACTIVE|PAUSED)(\s*</text>)',
            r'\g<1>' + badge_color + r'\2' + badge_text + r'\3',
            svg
        )

        # BOX 2: RING
        svg = re.sub(
            r'(<!-- STREAK RING & NUMBER -->[\s\S]*?<circle[^>]*\bstroke-dasharray=")[^"]*(")',
            r'\g<1>' + ring_dash + r'\2',
            svg
        )

        # BOX 2: FLAME
        if stats["is_active"]:
            svg = re.sub(
                r'(<!-- Flame icon -->[\s\S]*?<path[^>]*\bopacity=")[^"]*("\s+filter="url\(#glow\)")',
                r'\g<1>.25\2',
                svg
            )
            svg = re.sub(
                r'(<!-- Flame icon -->[\s\S]*?<!-- flame body -->\s*<path\b[^>]*?)\s+opacity="[^"]*"([^>]*>)',
                r'\g<1>\2',
                svg
            )
        else:
            svg = re.sub(
                r'(<!-- Flame icon -->[\s\S]*?<path[^>]*\bopacity=")[^"]*("\s+filter="url\(#glow\)")',
                r'\g<1>0\2',
                svg
            )
            if '<!-- flame body -->' in svg:
                svg = re.sub(
                    r'(<!-- Flame icon -->[\s\S]*?<!-- flame body -->\s*<path\b(?![^>]*\bopacity=)[^>]*?)(/?>)',
                    r'\g<1> opacity=".3"\2',
                    svg
                )

        # BOX 3: NUMBER
        svg = re.sub(
            r'(<!-- BOX 3 — LONGEST STREAK -->[\s\S]*?<!-- NUMBER -->[\s\S]*?<text[^>]*>\s*)(?:\{\{LONGEST_STREAK\}\}|\d+)(\s*</text>)',
            r'\g<1>' + str(stats["longest_streak"]) + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 3 — LONGEST STREAK -->[\s\S]*?<text x="778"\s+y="72"[^>]*>\s*)(?:\{\{LONGEST_STREAK\}\}|\d+)(\s*</text>)',
            r'\g<1>' + str(stats["longest_streak"]) + r'\2',
            svg
        )

        # BOX 3: RANGE
        svg = re.sub(
            r'(<!-- BOX 3 — LONGEST STREAK -->[\s\S]*?<!-- RANGE -->[\s\S]*?<text[^>]*>\s*)[^<\n]+?(\s*</text>)',
            r'\g<1>' + f'{stats["longest_from"]} → {stats["longest_to"]}' + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 3 — LONGEST STREAK -->[\s\S]*?<text x="724"\s+y="94"[^>]*>\s*)[^<\n]+?(\s*</text>)',
            r'\g<1>' + f'{stats["longest_from"]} → {stats["longest_to"]}' + r'\2',
            svg
        )

        with open(output_path, "w", encoding="utf-8") as file:
            file.write(svg)

        print(f"{output_path} updated successfully.")


def update_contribution_graph(days):
    # Use the latest 31 contribution days
    recent_days = days[-31:]

    points = []
    dates = []

    peak = max(
        (item["count"] for item in recent_days),
        default=0
    )

    for index, item in enumerate(recent_days):
        x = index * 37
        count = item["count"]

        # Keep the graph scale at 0 / 1 / 2+
        if count <= 0:
            y = 140
        elif count == 1:
            y = 70
        else:
            y = 0

        points.append(f"{x},{y}")
        dates.append(f'<text x="{x}" y="163">{item["date"].day}</text>')

    points_str = " ".join(points)
    dates_str = "\n    ".join(dates)

    graph_files = [
        {
            "filename": "contribution-history.svg",
            "is_dark": True
        },
        {
            "filename": "contribution-history-light.svg",
            "is_dark": False
        }
    ]

    for cfg in graph_files:
        filename = cfg["filename"]
        is_dark = cfg["is_dark"]
        template_path = os.path.join("templates", filename)
        output_path = os.path.join("assets", filename)

        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as file:
                svg = file.read()
        else:
            with open(output_path, "r", encoding="utf-8") as file:
                svg = file.read()

        # Build circles for dark / light
        circles = []
        for index, item in enumerate(recent_days):
            x = index * 37
            count = item["count"]
            if count <= 0:
                y = 140
            elif count == 1:
                y = 70
            else:
                y = 0

            is_peak = (count == peak and count > 0)
            radius = 5 if is_peak else 4

            if is_dark:
                if is_peak:
                    circles.append(
                        f'<circle cx="{x}" cy="{y}" r="5" '
                        f'fill="#e7b45a" filter="url(#glow)"/>'
                    )
                else:
                    circles.append(
                        f'<circle cx="{x}" cy="{y}" r="{radius}" fill="#70c9bd"/>'
                    )
            else:
                point_fill = "#d99a32" if is_peak else "#3b9d92"
                circles.append(
                    f'<circle cx="{x}" cy="{y}" r="{radius}" '
                    f'fill="{point_fill}"/>'
                )

        circles_str = "\n    ".join(circles)

        # 1. Template placeholder replacements
        svg = svg.replace("{{GRAPH_POINTS}}", points_str)
        svg = svg.replace("{{GRAPH_POINTS_CIRCLES}}", circles_str)
        svg = svg.replace("{{GRAPH_DATES}}", dates_str)
        svg = svg.replace("{{PEAK_CONTRIBUTIONS}}", str(peak))

        # 2. Regex fallback in case placeholders were already replaced in output_path
        svg = re.sub(
            r'(<polyline[\s\S]*?\bpoints=[\'"])[^\'"]*([\'"])',
            r'\g<1>' + points_str + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- DATA POINTS -->[\s\S]*?<g[^>]*>)[\s\S]*?(</g>)',
            r'\g<1>\n    ' + circles_str + r'\n  \2',
            svg
        )
        svg = re.sub(
            r'(<!-- DATES -->[\s\S]*?<g[^>]*>)[\s\S]*?(</g>)',
            r'\g<1>\n    ' + dates_str + r'\n  \2',
            svg
        )
        svg = re.sub(
            r'PEAK → [^\s<]+ CONTRIBUTIONS',
            f'PEAK → {peak} CONTRIBUTIONS',
            svg
        )

        # 3. Ensure horizontal grid lines extend to full 31 days (1110)
        svg = re.sub(r'x2="1050"', 'x2="1110"', svg)

        # 4. Ensure complete vertical grid lines (31 lines from 0 to 1110)
        grid_lines = "\n    ".join(
            f'<line x1="{i * 37}" y1="0" x2="{i * 37}" y2="140"/>'
            for i in range(len(recent_days))
        )
        svg = re.sub(
            r'(<!-- VERTICAL GRID -->[\s\S]*?<g[^>]*>)[\s\S]*?(</g>)',
            r'\g<1>\n    ' + grid_lines + r'\n  \2',
            svg
        )

        with open(output_path, "w", encoding="utf-8") as file:
            file.write(svg)

        print(f"{output_path} updated successfully.")


def main():
    print(f"Fetching GitHub contributions for: {USERNAME}")

    days = get_contribution_days()

    stats = calculate_stats(days)

    print()
    print("GitHub statistics")
    print("-----------------")
    print("Total contributions:", stats["total"])
    print("Current streak:", stats["current_streak"])
    print("Active status:", stats["is_active"])
    print("Current streak range:", stats["current_streak_range"])
    print("Longest streak:", stats["longest_streak"])
    print("Longest streak span:", stats["longest_from"], "->", stats["longest_to"])
    print()

    update_svg(stats)
    update_contribution_graph(days)


if __name__ == "__main__":
    main()
