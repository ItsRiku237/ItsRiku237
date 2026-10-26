import os
import re
import json
import urllib.request
from datetime import date, timedelta


USERNAME = os.environ["GITHUB_USERNAME"]
TOKEN = os.environ["GITHUB_TOKEN"]

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


def get_contribution_days():

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


def calculate_stats(days):

    contribution_map = {
        item["date"]: item["count"]
        for item in days
    }

    total = sum(item["count"] for item in days)

    # -----------------------------------------
    # CURRENT STREAK
    # -----------------------------------------

    current_streak = 0

    cursor = TODAY

    # If today has no contribution,
    # start checking from yesterday.
    if contribution_map.get(cursor, 0) == 0:
        cursor -= timedelta(days=1)

    while contribution_map.get(cursor, 0) > 0:
        current_streak += 1
        cursor -= timedelta(days=1)

    current_streak_date = (
        TODAY
        if contribution_map.get(TODAY, 0) > 0
        else TODAY - timedelta(days=1)
    )


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

        "current_streak_date": current_streak_date.strftime("%b %d"),

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
    replacements = {
        "{{TOTAL_CONTRIBUTIONS}}":
            str(stats["total"]),

        "{{CURRENT_STREAK}}":
            str(stats["current_streak"]),

        "{{LONGEST_STREAK}}":
            str(stats["longest_streak"]),

        "{{CURRENT_STREAK_DATE}}":
            stats["current_streak_date"],

        "{{LONGEST_FROM}}":
            stats["longest_from"],

        "{{LONGEST_TO}}":
            stats["longest_to"],

        "{{TODAY}}":
            stats["today"],

        "{{TOTAL_FROM}}":
            stats["from_date"]
    }

    svg_files = [
        "github-stats.svg",
        "github-stats-light.svg"
    ]

    for filename in svg_files:
        template_path = os.path.join("templates", filename)
        output_path = os.path.join("assets", filename)

        if os.path.exists(template_path):
            with open(template_path, "r", encoding="utf-8") as file:
                svg = file.read()
        else:
            with open(output_path, "r", encoding="utf-8") as file:
                svg = file.read()

        for old, new in replacements.items():
            svg = svg.replace(old, new)

        # Fallback regex in case placeholders were already replaced
        svg = re.sub(
            r'(<!-- BOX 1 — TOTAL CONTRIBUTIONS -->[\s\S]*?<!-- NUMBER -->[\s\S]*?<text[^>]*>\s*)(?:\{\{TOTAL_CONTRIBUTIONS\}\}|\d+)(\s*</text>)',
            r'\g<1>' + str(stats["total"]) + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 1 — TOTAL CONTRIBUTIONS -->[\s\S]*?<text x="25"\s+y="94"[^>]*>\s*)[^<\n]+?(\s*</text>)',
            r'\g<1>' + f'{stats["from_date"]} → {stats["today"]}' + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 2 — CURRENT STREAK -->[\s\S]*?<g transform="translate\(485 69\)"[\s\S]*?<text[^>]*>\s*)(?:\{\{CURRENT_STREAK\}\}|\d+)(\s*</text>)',
            r'\g<1>' + str(stats["current_streak"]) + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 2 — CURRENT STREAK -->[\s\S]*?<text x="374"\s+y="94"[^>]*>\s*ACTIVE →\s*)[^<\n]+?(\s*</text>)',
            r'\g<1>' + f'ACTIVE → {stats["current_streak_date"]}' + r'\2',
            svg
        )
        svg = re.sub(
            r'(<!-- BOX 3 — LONGEST STREAK -->[\s\S]*?<text x="778"\s+y="72"[^>]*>\s*)(?:\{\{LONGEST_STREAK\}\}|\d+)(\s*</text>)',
            r'\g<1>' + str(stats["longest_streak"]) + r'\2',
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
    print("Longest streak:", stats["longest_streak"])
    print("Longest streak:", stats["longest_from"], "->", stats["longest_to"])
    print()

    update_svg(stats)
    update_contribution_graph(days)


if __name__ == "__main__":
    main()