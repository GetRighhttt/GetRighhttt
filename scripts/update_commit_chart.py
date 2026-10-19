"""Fetch GitHub-credited commits and save a README-safe SVG. Uses the workflow token."""
import datetime as dt
from html import escape
import json
import os
from pathlib import Path
import urllib.request

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      commitContributionsByRepository(maxRepositories: 100) {
        contributions(first: 100) {
          nodes { occurredAt commitCount }
          pageInfo { hasNextPage }
        }
      }
    }
  }
}
"""


def daily_counts(collection, start, end):
    counts = {start + dt.timedelta(days=i): 0 for i in range((end - start).days + 1)}
    for repository in collection["commitContributionsByRepository"]:
        contributions = repository["contributions"]
        if contributions["pageInfo"]["hasNextPage"]:
            raise RuntimeError("GitHub returned incomplete commit data; keeping the previous chart.")
        for node in contributions["nodes"]:
            day = dt.datetime.fromisoformat(node["occurredAt"].replace("Z", "+00:00")).astimezone(dt.timezone.utc).date()
            if day not in counts or node["commitCount"] < 0:
                raise RuntimeError("GitHub returned unexpected commit data; keeping the previous chart.")
            counts[day] += node["commitCount"]
    if sum(counts.values()) != collection["totalCommitContributions"]:
        raise RuntimeError("GitHub's totals differ from the returned commits; keeping the previous chart.")
    return counts


def render_svg(counts, username):
    dates, values = list(counts.keys()), list(counts.values())
    left, right, top, bottom = 65, 935, 100, 240
    peak = max(max(values), 1)
    points = [(left + i * (right - left) / (len(values) - 1), bottom - value * (bottom - top) / peak)
              for i, value in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    name = escape(username)
    total = sum(values)
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="310" viewBox="0 0 1000 310" role="img" aria-labelledby="title desc">
<title id="title">{name}: commits over the last 90 days</title>
<desc id="desc">{total} commits credited by GitHub between {dates[0]} and {dates[-1]}. Daily counts in UTC.</desc>
<rect width="1000" height="310" rx="18" fill="#111827"/>
<g font-family="Arial, Helvetica, sans-serif">
<text x="36" y="40" fill="#f9fafb" font-size="22" font-weight="700">Recent commits</text>
<text x="36" y="68" fill="#cbd5e1" font-size="14">{name} · {total:,} commits · last 90 days</text>''']
    for fraction in (0, 0.5, 1):
        y = bottom - fraction * (bottom - top)
        parts.append(f'<path d="M{left} {y}H{right}" stroke="#293447"/><text x="52" y="{y + 5}" text-anchor="end" fill="#94a3b8" font-size="12">{peak * fraction:g}</text>')
    parts += [f'<polygon points="{left},{bottom} {line} {right},{bottom}" fill="#75e3ce" opacity="0.10"/>',
              f'<polyline points="{line}" fill="none" stroke="#75e3ce" stroke-width="2.5" stroke-linejoin="round"/>',
              f'<text x="{left}" y="263" fill="#94a3b8" font-size="12">{dates[0]:%b %d}</text>',
              f'<text x="{right}" y="263" text-anchor="end" fill="#94a3b8" font-size="12">{dates[-1]:%b %d}</text>',
              '<text x="36" y="291" fill="#94a3b8" font-size="11">GitHub-credited commits visible to the workflow · UTC · refreshed daily</text>',
              '</g></svg>']
    return "\n".join(parts) + "\n"


def main():
    username = os.environ.get("PROFILE_USERNAME", "GetRighhttt")
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GH_TOKEN is required. Run this through the Commit chart GitHub workflow.")
    now = dt.datetime.now(dt.timezone.utc)
    start = now.date() - dt.timedelta(days=89)
    variables = {"login": username, "from": f"{start}T00:00:00Z", "to": now.isoformat()}
    request = urllib.request.Request(
        "https://api.github.com/graphql", data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-commit-chart"})
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
    if result.get("errors") or not result.get("data", {}).get("user"):
        raise RuntimeError("GitHub could not return commit data; keeping the previous chart.")
    collection = result["data"]["user"]["contributionsCollection"]
    counts = daily_counts(collection, start, now.date())
    target = Path(__file__).resolve().parents[1] / "assets/commit-chart.svg"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(render_svg(counts, username), encoding="utf-8")
    temporary.replace(target)
    print(f"Updated {target.name} with {sum(counts.values())} commits.")


if __name__ == "__main__":
    main()
