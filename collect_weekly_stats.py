import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


def get_weeks_in_range(start_date: str, end_date: str) -> list[tuple[str, str, int]]:
    """
    Generate list of (start, end, week_number) tuples for each week.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        List of tuples: (week_start, week_end, iso_week_number)
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    weeks = []
    current = start

    while current <= end:
        week_start = current
        week_end = min(current + timedelta(days=6), end)
        iso_week = week_start.isocalendar()[1]
        year = week_start.year

        weeks.append((
            week_start.strftime("%Y-%m-%d"),
            week_end.strftime("%Y-%m-%d"),
            f"{year}-W{iso_week:02d}"
        ))

        current = week_end + timedelta(days=1)

    return weeks


def collect_week_stats(org: str, repo: str, workflow: str,
                       week_start: str, week_end: str, week_num: str,
                       output_dir: Path, jobs: bool = False) -> bool:
    """
    Collect stats for a single week.

    Args:
        jobs: If True, collect job stats instead of workflow run stats

    Returns:
        True if successful, False otherwise
    """
    prefix = "job-stats" if jobs else "workflow-stats"
    output_file = output_dir / f"{prefix}-{week_num}.json"

    print(f"Collecting {week_num} ({week_start} to {week_end})...", end=" ", flush=True)

    cmd = [
        "gh", "workflow-stats",
        "-o", org,
        "-r", repo,
        "-f", workflow,
        "-A",
        "-c", f"{week_start}..{week_end}",
    ]

    if jobs:
        cmd.append("jobs")

    cmd.append("--json")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0 and result.stdout.strip():
            output_file.write_text(result.stdout)

            # Check if file has meaningful data
            if output_file.stat().st_size > 100:
                print(f"✓ ({output_file.stat().st_size} bytes)")
                return True
            else:
                print("⚠ (empty)")
                output_file.unlink()
                return False
        else:
            print("✗ (failed)")
            if result.stderr:
                print(f"  Error: {result.stderr.strip()}")
            return False

    except subprocess.TimeoutExpired:
        print("✗ (timeout)")
        return False
    except Exception as e:
        print(f"✗ (error: {e})")
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Collect GitHub workflow stats by week"
    )
    parser.add_argument(
        "-o", "--org",
        required=True,
        help="GitHub organization"
    )
    parser.add_argument(
        "-r", "--repo",
        required=True,
        help="Repository name"
    )
    parser.add_argument(
        "-w", "--workflow",
        required=True,
        help="Workflow file name (e.g., on-pr.yml)"
    )
    parser.add_argument(
        "-s", "--start",
        required=True,
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "-e", "--end",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD, default: today)"
    )
    parser.add_argument(
        "-d", "--dir",
        default=None,
        help="Output directory (default: weekly-stats or weekly-stats-jobs depending on --jobs flag)"
    )
    parser.add_argument(
        "-j", "--jobs",
        action="store_true",
        help="Collect job statistics instead of workflow run statistics"
    )

    args = parser.parse_args()

    # Check if gh CLI is installed
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Error: gh CLI is not installed or not in PATH", file=sys.stderr)
        print("Install from: https://cli.github.com/", file=sys.stderr)
        sys.exit(1)

    # Check if gh-workflow-stats extension is installed
    result = subprocess.run(["gh", "extension", "list"], capture_output=True, text=True)
    if "fchimpan/gh-workflow-stats" not in result.stdout:
        print("Error: gh-workflow-stats extension is not installed", file=sys.stderr)
        print("Install with: gh extension install fchimpan/gh-workflow-stats", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    if args.dir:
        output_dir = Path(args.dir)
    else:
        output_dir = Path("weekly-stats-jobs" if args.jobs else "weekly-stats")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Configuration:")
    print(f"  Organization: {args.org}")
    print(f"  Repository: {args.repo}")
    print(f"  Workflow: {args.workflow}")
    print(f"  Date range: {args.start} to {args.end}")
    print(f"  Mode: {'Jobs' if args.jobs else 'Workflow runs'}")
    print(f"  Output directory: {output_dir}")
    print()

    # Generate weeks
    weeks = get_weeks_in_range(args.start, args.end)
    print(f"Collecting data for {len(weeks)} weeks...\n")

    # Collect stats for each week
    successful = 0
    failed = 0

    for week_start, week_end, week_num in weeks:
        if collect_week_stats(args.org, args.repo, args.workflow,
                             week_start, week_end, week_num, output_dir, args.jobs):
            successful += 1
        else:
            failed += 1

    # Summary
    print()
    print("=" * 60)
    print(f"Collection complete!")
    print(f"  Successful: {successful}")
    print(f"  Failed/Empty: {failed}")
    print(f"  Output directory: {output_dir}")
    print()
    if not args.jobs:
        print(f"Run analysis with:")
        print(f"  python main.py {output_dir}/workflow-stats-*.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
