import argparse
import json
import sys
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use('Agg')  # Use non-interactive backend


def load_workflow_stats(filepaths: list[str]) -> list[dict]:
    """Load one or more workflow stats JSON files."""
    data_list = []

    for filepath in filepaths:
        path = Path(filepath)
        if not path.exists():
            print(f"Error: File '{filepath}' not found!", file=sys.stderr)
            sys.exit(1)

        print(f"  Loading: {filepath}")
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                data_list.append(data)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in '{filepath}': {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: Failed to read '{filepath}': {e}", file=sys.stderr)
            sys.exit(1)

    return data_list


def extract_successful_runs(data_list: list[dict]) -> tuple[list[dict], int]:
    """Extract all successful workflow runs from one or more data files.

    Returns:
        tuple: (list of runs with run_attempt==1, total count of all runs including retries)
    """
    all_runs = []
    total_runs_count = 0

    for data in data_list:
        # Navigate to the success section
        conclusions = data.get('workflow_runs_stats_summary', {}).get('conclusions', {})
        success_data = conclusions.get('success', {})

        if not success_data:
            continue

        workflow_runs = success_data.get('workflow_runs', [])

        for run in workflow_runs:
            # Extract the date from run_started_at
            run_started_at = run.get('run_started_at')
            duration = run.get('duration')

            # Exlcude very fast runs.
            if int(duration) < 2*60:
                continue

            # Count this run in the total
            total_runs_count += 1

            # To get comparable timings we nly pick the run attempt 1. This means we only pick runs that passed without
            # retry, and due to the flakyness of CI this reduces the number of runs we use for stats by about half.
            run_attempt = run.get('run_attempt')
            if run_attempt != 1:
                continue

            if run_started_at and duration is not None:
                all_runs.append({
                    'date': run_started_at,
                    'duration': duration,
                    'id': run.get('id'),
                    'actor': run.get('actor'),
                })

    # Remove duplicates based on run ID
    seen_ids = set()
    unique_runs = []
    for run in all_runs:
        if run['id'] not in seen_ids:
            seen_ids.add(run['id'])
            unique_runs.append(run)

    return unique_runs, total_runs_count


def plot_durations(runs: list[dict], total_runs: int, output_file: str = "workflow_durations.png", bucket_days: int = 1):
    """Plot the workflow durations by date.

    Args:
        runs: List of workflow run data (run_attempt==1 only)
        total_runs: Total number of runs including retries
        output_file: Output filename for the plot
        bucket_days: Number of days to group data by (default: 1 for daily)
    """
    if not runs:
        print("No data to plot!", file=sys.stderr)
        sys.exit(1)

    # Convert to pandas DataFrame for easier manipulation
    df = pd.DataFrame(runs)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')

    # Convert duration from seconds to minutes for better readability
    df['duration_minutes'] = df['duration'] / 60

    # Group by bucket_days and calculate statistics
    if bucket_days == 1:
        # Daily grouping
        df['bucket'] = df['date'].dt.date
        bucket_label = 'Daily'
    else:
        # Group by N days
        min_date = df['date'].min()
        df['bucket'] = ((df['date'] - min_date).dt.days // bucket_days) * bucket_days
        df['bucket'] = min_date + pd.to_timedelta(df['bucket'], unit='D')
        bucket_label = f'{bucket_days}-Day'

    bucket_stats = df.groupby('bucket').agg({
        'duration_minutes': ['mean', 'std', 'count']
    }).reset_index()
    bucket_stats.columns = ['date', 'mean', 'std', 'count']

    # Convert date back to datetime for plotting
    bucket_stats['date'] = pd.to_datetime(bucket_stats['date'])

    # Create the plot
    plt.figure(figsize=(14, 8))

    # Bar chart with error bars
    plt.bar(bucket_stats['date'], bucket_stats['mean'],
            yerr=bucket_stats['std'],
            alpha=0.7,
            color='#2E86AB',
            edgecolor='#1a5278',
            linewidth=1.5,
            error_kw={'ecolor': '#d62828', 'linewidth': 2, 'capsize': 5, 'alpha': 0.8},
            width=bucket_days * 0.8)

    # Formatting
    plt.xlabel('Date', fontsize=12, fontweight='bold')
    plt.ylabel('Average Duration (minutes)', fontsize=12, fontweight='bold')
    plt.title(f'{bucket_label} Average Workflow Run Durations - Successful Runs Only',
              fontsize=14, fontweight='bold', pad=20)

    # Format x-axis to show dates nicely
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.xticks(rotation=45, ha='right')

    # Add grid for better readability (only horizontal)
    plt.grid(True, alpha=0.3, linestyle='--', axis='y')

    # Add statistics as text
    stats_text = f"Initial Runs (attempt=1): {len(df)}\n"
    stats_text += f"Total Runs (all attempts, not plotted): {total_runs}\n"
    retry_rate = ((total_runs - len(df)) / total_runs * 100) if total_runs > 0 else 0
    stats_text += f"Retry rate: {retry_rate:.1f}%\n"

    stats_text += f"Bucket Size: {bucket_days} day(s)\n"
    stats_text += f"Avg Duration: {df['duration_minutes'].mean():.1f} min\n"
    stats_text += f"Min Duration: {df['duration_minutes'].min():.1f} min\n"
    stats_text += f"Max Duration: {df['duration_minutes'].max():.1f} min\n"
    stats_text += f"Overall Std Dev: {df['duration_minutes'].std():.1f} min"

    plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes,
             fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # Add note about error bars
    note_text = f'Error bars show standard deviation per {bucket_days}-day bucket' if bucket_days > 1 else 'Error bars show standard deviation per day'
    plt.text(0.98, 0.02, note_text,
             transform=plt.gca().transAxes,
             fontsize=9, verticalalignment='bottom', horizontalalignment='right',
             style='italic', alpha=0.7)

    plt.tight_layout()

    # Save the plot
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Plot saved to: {output_file}")

    # Show summary statistics
    print("\n=== Summary Statistics ===")
    print(f"Initial runs (attempt=1): {len(df)}")
    print(f"Total runs (all attempts): {total_runs}")
    retry_rate = ((total_runs - len(df)) / total_runs * 100) if total_runs > 0 else 0
    print(f"Retry rate: {retry_rate:.1f}%")
    print(f"Date range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
    print(f"Average duration: {df['duration_minutes'].mean():.2f} minutes")
    print(f"Median duration: {df['duration_minutes'].median():.2f} minutes")
    print(f"Minimum duration: {df['duration_minutes'].min():.2f} minutes")
    print(f"Maximum duration: {df['duration_minutes'].max():.2f} minutes")
    print(f"Standard deviation: {df['duration_minutes'].std():.2f} minutes")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Plot workflow run durations from gh-workflow-stats JSON output"
    )
    parser.add_argument(
        'input_files',
        nargs='*',
        default=['workflow-stats.json'],
        help='Path(s) to workflow-stats JSON file(s) (default: workflow-stats.json)'
    )
    parser.add_argument(
        '-o', '--output',
        default='workflow_durations.png',
        help='Output file for the plot (default: workflow_durations.png)'
    )
    parser.add_argument(
        '-b', '--bucket-days',
        type=int,
        default=1,
        help='Number of days to group data by (default: 1 for daily aggregation)'
    )

    args = parser.parse_args()

    # Handle default case
    if not args.input_files:
        args.input_files = ['workflow-stats.json']

    print(f"Loading workflow stats from {len(args.input_files)} file(s)...")
    data_list = load_workflow_stats(args.input_files)

    print("Extracting successful runs...")
    runs, total_runs = extract_successful_runs(data_list)

    print(f"Found {len(runs)} initial runs (run_attempt=1, after deduplication)")
    print(f"Total runs including retries: {total_runs}")

    if runs:
        print("Creating plot...")
        if args.bucket_days != 1:
            print(f"Grouping data into {args.bucket_days}-day buckets...")
        plot_durations(runs, total_runs, args.output, args.bucket_days)
    else:
        print("No successful runs to plot!", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
