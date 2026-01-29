# CI Stats - Workflow Duration Analyzer

> [!WARNING]
> This is AI generated code that has not been thorougly reviewed.

Visualize GitHub Actions workflow run durations from data collected by [gh-workflow-stats](https://github.com/fchimpan/gh-workflow-stats).

## Dependencies

The scripts use [gh](https://cli.github.com/manual/gh) and [gh-workflow-stats](https://github.com/fchimpan/gh-workflow-stats).

Install `gh` using the instructions https://github.com/cli/cli#installation and then install the gh-workflow-stats extension.

```bash
gh extension install fchimpan/gh-workflow-stats
```

## Collect Data

The `collect_weekly_stats.py` script collects stats chunked by calendar weeks.

```bash
uv run python collect_weekly_stats.py --org pulumi --repo pulumi --workflow on-pr.yml --start 2026-01-01 --end 2026-01-31 --dir weekly-stats-on-pr
```

```bash
uv run python collect_weekly_stats.py --org pulumi --repo pulumi --workflow on-merge.yml --start 2026-01-01 --end 2026-01-31 --dir weekly-stats-on-merge
```

## Analyze Data

The `main.py` script parses the stats files and creates a png graph.

```bash
uv run python main.py weekly-stats-on-pr/workflow-stats-*.json --bucket-days 7 --output on-pr.png
```

```bash
uv run python main.py weekly-stats-on-merge/workflow-stats-*.json --bucket-days 7 --output on-merge.png
```

### collect_weekly_stats.py
- `-o, --org`: GitHub organization (required)
- `-r, --repo`: Repository name (required)
- `-w, --workflow`: Workflow file name (required)
- `-s, --start`: Start date YYYY-MM-DD (required)
- `-e, --end`: End date YYYY-MM-DD (default: today)
- `-d, --dir`: Output directory (default: weekly-stats)

### main.py
- `input_files`: One or more JSON files (supports globs)
- `-o, --output`: Output PNG filename (default: workflow_durations.png)
- `-b, --bucket-days`: Days to group by (default: 1 for daily)
