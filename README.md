# CI Stats - Workflow Duration Analyzer

Visualize GitHub Actions workflow run durations from data collected by [gh-workflow-stats](https://github.com/fchimpan/gh-workflow-stats).

## Dependencies

```bash
# Install gh-workflow-stats extension
gh extension install fchimpan/gh-workflow-stats
```

## Collect Data

```bash
uv run python collect_weekly_stats.py --org pulumi --repo pulumi --workflow on-pr.yml --start 2025-01-01 --end 2025-12-31
```

This creates files like `weekly-stats/workflow-stats-2025-W01.json`, `weekly-stats/workflow-stats-2025-W02.json`, etc.

## Analyze Data

```bash
uv run python main.py weekly-stats/workflow-stats-*.json --bucket-days 7 --output weekly.png

uv run python main.py weekly-stats/workflow-stats-*.json --bucket-days 30 --output monthly.png
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

## Notes

- Only successful runs are analyzed
- Multiple files are automatically deduplicated by run ID
- Weekly collection prevents gh-workflow-stats crashes on large datasets
- Error bars show standard deviation within each bucket
