import os
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

    variables = {
        "login": USERNAME,
        "from": f"{START_DATE.isoformat()}T00:00:00Z",
        "to": f"{TODAY.isoformat()}T23:59:59Z"
    }

    result = github_graphql(GRAPHQL, variables)

    if "errors" in result:
        raise RuntimeError(json.dumps(result["errors"], indent=2))

    calendar = result["data"]["user"]["contributionsCollection"]["contributionCalendar"]

    days = []

    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            days.append({
                "date": date.fromisoformat(day["date"]),
                "count": day["contributionCount"]
            })

    days.sort(key=lambda x: x["date"])

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

    # Update BOTH dark and light SVG files
    svg_paths = [
        "assets/github-stats.svg",
        "assets/github-stats-light.svg"
    ]

    for svg_path in svg_paths:

        with open(svg_path, "r", encoding="utf-8") as file:
            svg = file.read()

        for old, new in replacements.items():
            svg = svg.replace(old, new)

        with open(svg_path, "w", encoding="utf-8") as file:
            file.write(svg)

        print(f"{svg_path} updated successfully.")


def update_contribution_graph(days):
    svg_path = "assets/contribution-history-light.svg"

    with open(svg_path, "r", encoding="utf-8") as file:
        svg = file.read()

    # Use the latest 31 contribution days
    recent_days = days[-31:]

    points = []
    circles = []
    dates = []

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

        radius = 5 if count == max(d["count"] for d in recent_days) else 4

        point_fill = "#d99a32" if count == max(
            d["count"] for d in recent_days
        ) and count > 0 else "#3b9d92"

        circles.append(
            f'<circle cx="{x}" cy="{y}" r="{radius}" '
            f'fill="{point_fill}"/>'
        )

        dates.append(
            f'<text x="{x}" y="163">'
            f'{item["date"].day}</text>'
        )

    peak = max(
        (item["count"] for item in recent_days),
        default=0
    )

    svg = svg.replace(
        "{{GRAPH_POINTS}}",
        " ".join(points)
    )

    svg = svg.replace(
        "{{GRAPH_POINTS_CIRCLES}}",
        "\n    ".join(circles)
    )

    svg = svg.replace(
        "{{GRAPH_DATES}}",
        "\n    ".join(dates)
    )

    svg = svg.replace(
        "{{PEAK_CONTRIBUTIONS}}",
        str(peak)
    )

    with open(svg_path, "w", encoding="utf-8") as file:
        file.write(svg)

    print("contribution-history-light.svg updated successfully.")



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
    print("Longest streak:", stats["longest_from"], "→", stats["longest_to"])
    print()

    update_svg(stats)

    print("github-stats.svg updated successfully.")
    update_contribution_graph(days)


if __name__ == "__main__":
    main()