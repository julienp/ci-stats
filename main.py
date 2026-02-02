import argparse
import json
import sys
from collections import defaultdict
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


def extract_successful_runs(data_list: list[dict]) -> tuple[list[dict], int, list[dict]]:
    """Extract all successful workflow runs from one or more data files.

    Returns:
        tuple: (list of successful runs with run_attempt==1,
                total count of successful runs including retries,
                list of all runs (successful and failed) with run_attempt==1 for success rate calculation)
    """
    all_runs = []
    total_runs_count = 0
    all_runs_for_rate = []  # All runs (success + failure) with run_attempt==1

    for data in data_list:
        # Navigate to the conclusions section
        conclusions = data.get('workflow_runs_stats_summary', {}).get('conclusions', {})

        # Process successful runs
        success_data = conclusions.get('success', {})
        if success_data:
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

                run_attempt = run.get('run_attempt')

                # Add to all_runs_for_rate if run_attempt==1
                if run_attempt == 1 and run_started_at:
                    all_runs_for_rate.append({
                        'date': run_started_at,
                        'success': True,
                        'id': run.get('id'),
                    })

                # To get comparable timings we nly pick the run attempt 1. This means we only pick runs that passed without
                # retry, and due to the flakyness of CI this reduces the number of runs we use for stats by about half.
                if run_attempt != 1:
                    continue

                if run_started_at and duration is not None:
                    all_runs.append({
                        'date': run_started_at,
                        'duration': duration,
                        'id': run.get('id'),
                        'actor': run.get('actor'),
                    })

        # Process failed runs (for success rate calculation)
        failure_data = conclusions.get('failure', {})
        if failure_data:
            workflow_runs = failure_data.get('workflow_runs', [])

            for run in workflow_runs:
                run_started_at = run.get('run_started_at')
                duration = run.get('duration')

                # Exlcude very fast runs.
                if duration and int(duration) < 2*60:
                    continue

                run_attempt = run.get('run_attempt')

                # Add to all_runs_for_rate if run_attempt==1
                if run_attempt == 1 and run_started_at:
                    all_runs_for_rate.append({
                        'date': run_started_at,
                        'success': False,
                        'id': run.get('id'),
                    })

    # Remove duplicates based on run ID
    seen_ids = set()
    unique_runs = []
    for run in all_runs:
        if run['id'] not in seen_ids:
            seen_ids.add(run['id'])
            unique_runs.append(run)

    # Remove duplicates from all_runs_for_rate
    seen_ids_rate = set()
    unique_runs_for_rate = []
    for run in all_runs_for_rate:
        if run['id'] not in seen_ids_rate:
            seen_ids_rate.add(run['id'])
            unique_runs_for_rate.append(run)

    return unique_runs, total_runs_count, unique_runs_for_rate


def plot_durations(runs: list[dict], total_runs: int, all_runs_for_rate: list[dict], output_file: str = "workflow_durations.png", bucket_days: int = 1):
    """Plot the workflow durations by date with success rate overlay.

    Args:
        runs: List of successful workflow run data (run_attempt==1 only)
        total_runs: Total number of successful runs including retries
        all_runs_for_rate: List of all runs (success and failure) for success rate calculation
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

    # Calculate success rate per bucket
    df_rate = pd.DataFrame(all_runs_for_rate)
    df_rate['date'] = pd.to_datetime(df_rate['date'])

    # Group by the same bucket logic
    if bucket_days == 1:
        df_rate['bucket'] = df_rate['date'].dt.date
    else:
        min_date_rate = df_rate['date'].min()
        df_rate['bucket'] = ((df_rate['date'] - min_date_rate).dt.days // bucket_days) * bucket_days
        df_rate['bucket'] = min_date_rate + pd.to_timedelta(df_rate['bucket'], unit='D')

    rate_stats = df_rate.groupby('bucket').agg({
        'success': ['sum', 'count']
    }).reset_index()
    rate_stats.columns = ['date', 'success_count', 'total_count']
    rate_stats['success_rate'] = (rate_stats['success_count'] / rate_stats['total_count']) * 100
    rate_stats['date'] = pd.to_datetime(rate_stats['date'])

    # Create the plot with two y-axes
    fig, ax1 = plt.subplots(figsize=(14, 8))

    # Primary axis: Duration bar chart with error bars
    ax1.bar(bucket_stats['date'], bucket_stats['mean'],
            yerr=bucket_stats['std'],
            alpha=0.7,
            color='#2E86AB',
            edgecolor='#1a5278',
            linewidth=1.5,
            error_kw={'ecolor': '#d62828', 'linewidth': 2, 'capsize': 5, 'alpha': 0.8},
            width=bucket_days * 0.8,
            label='Avg Duration')

    # Secondary axis: Success rate line
    ax2 = ax1.twinx()
    ax2.plot(rate_stats['date'], rate_stats['success_rate'],
             color='#06A77D', linewidth=2.5, marker='o', markersize=6,
             label='Success Rate', alpha=0.9)

    # Formatting for primary axis (duration)
    ax1.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Average Duration (minutes)', fontsize=12, fontweight='bold', color='#2E86AB')
    ax1.tick_params(axis='y', labelcolor='#2E86AB')

    # Formatting for secondary axis (success rate)
    ax2.set_ylabel('Success Rate (%)', fontsize=12, fontweight='bold', color='#06A77D')
    ax2.tick_params(axis='y', labelcolor='#06A77D')
    ax2.set_ylim(0, 100)

    # Title
    ax1.set_title(f'{bucket_label} Average Workflow Run Durations - Successful Runs Only',
                  fontsize=14, fontweight='bold', pad=20)

    # Format x-axis to show dates nicely
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Add grid for better readability (only horizontal)
    ax1.grid(True, alpha=0.3, linestyle='--', axis='y')

    # Add legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')

    # Add statistics as text
    stats_text = f"Successful Initial Runs (attempt=1): {len(df)}\n"
    overall_success_rate = (len(df) / len(df_rate) * 100) if len(df_rate) > 0 else 0
    stats_text += f"Overall Success Rate: {overall_success_rate:.1f}%\n"
    stats_text += f"Avg Duration: {df['duration_minutes'].mean():.1f} min\n"
    stats_text += f"Min Duration: {df['duration_minutes'].min():.1f} min\n"
    stats_text += f"Max Duration: {df['duration_minutes'].max():.1f} min\n"
    stats_text += f"Overall Std Dev: {df['duration_minutes'].std():.1f} min"

    ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes,
             fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # Add note about error bars
    note_text = f'Error bars show standard deviation per {bucket_days}-day bucket' if bucket_days > 1 else 'Error bars show standard deviation per day'
    ax1.text(0.98, 0.02, note_text,
             transform=ax1.transAxes,
             fontsize=9, verticalalignment='bottom', horizontalalignment='right',
             style='italic', alpha=0.7)

    plt.tight_layout()

    # Save the plot
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Plot saved to: {output_file}")

    # Show summary statistics
    print("\n=== Summary Statistics ===")
    print(f"Successful initial runs (attempt=1): {len(df)}")
    print(f"Overall success rate: {overall_success_rate:.1f}%")
    retry_rate = ((total_runs - len(df)) / total_runs * 100) if total_runs > 0 else 0
    print(f"Retry rate (successful runs): {retry_rate:.1f}%")
    print(f"Date range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
    print(f"Average duration: {df['duration_minutes'].mean():.2f} minutes")
    print(f"Median duration: {df['duration_minutes'].median():.2f} minutes")
    print(f"Minimum duration: {df['duration_minutes'].min():.2f} minutes")
    print(f"Maximum duration: {df['duration_minutes'].max():.2f} minutes")
    print(f"Standard deviation: {df['duration_minutes'].std():.2f} minutes")


def load_job_stats(filepaths: list[str]) -> list[tuple[str, dict]]:
    """Load one or more job stats JSON files.

    Returns:
        List of tuples: (filename/week_identifier, data)
    """
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
                # Extract week identifier from filename (e.g., "2026-W01" from "job-stats-2026-W01.json")
                filename = path.stem
                week_id = filename.replace('job-stats-', '')
                data_list.append((week_id, data))
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in '{filepath}': {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: Failed to read '{filepath}': {e}", file=sys.stderr)
            sys.exit(1)

    # Sort by week identifier
    data_list.sort(key=lambda x: x[0])
    return data_list


def extract_job_durations(data_list: list[tuple[str, dict]]) -> dict:
    """Extract job durations over time from multiple job stats files.

    Returns:
        dict: {job_name: [(week_id, avg_duration_seconds, run_count), ...]}
    """
    job_durations = defaultdict(list)

    for week_id, data in data_list:
        if 'workflow_jobs_stats_summary' not in data:
            print(f"Warning: No job stats in {week_id}, skipping", file=sys.stderr)
            continue

        jobs = data['workflow_jobs_stats_summary']

        for job in jobs:
            job_name = job['name']
            avg_duration = job['execution_duration_stats']['avg']
            run_count = job['total_runs_count']

            # Only include jobs with actual runs
            if run_count > 0 and avg_duration > 0:
                job_durations[job_name].append((week_id, avg_duration, run_count))

    return dict(job_durations)


def plot_job_durations(job_durations: dict, output_file: str = "job_durations.png", top_n: int = 10):
    """Plot line graphs for the top N slowest jobs over time.

    Args:
        job_durations: Dict of {job_name: [(week_id, avg_duration_seconds, run_count), ...]}
        output_file: Output filename for the plot
        top_n: Number of top slowest jobs to plot
    """
    if not job_durations:
        print("No job duration data to plot!", file=sys.stderr)
        sys.exit(1)

    # Calculate overall average duration for each job
    job_avg_durations = {}
    for job_name, durations in job_durations.items():
        # Weight by run count
        total_duration_weighted = sum(dur * count for _, dur, count in durations)
        total_runs = sum(count for _, _, count in durations)
        if total_runs > 0:
            job_avg_durations[job_name] = total_duration_weighted / total_runs

    # Get top N slowest jobs
    slowest_jobs = sorted(job_avg_durations.items(), key=lambda x: x[1], reverse=True)[:top_n]
    slowest_job_names = [name for name, _ in slowest_jobs]

    print(f"\nTop {top_n} slowest jobs (by weighted average):")
    for i, (name, avg_dur) in enumerate(slowest_jobs, 1):
        print(f"  {i}. {name}: {avg_dur/60:.1f} minutes")

    # Create the plot - adjust figure size to accommodate legend below
    fig, ax = plt.subplots(figsize=(18, 10))

    # Use a color palette
    colors = plt.cm.tab10(np.linspace(0, 1, top_n))

    # Plot each job
    for idx, job_name in enumerate(slowest_job_names):
        durations = job_durations[job_name]
        weeks = [d[0] for d in durations]
        avg_durations_min = [d[1] / 60 for d in durations]  # Convert to minutes

        ax.plot(weeks, avg_durations_min,
                marker='o', linewidth=2, markersize=6,
                label=job_name, color=colors[idx], alpha=0.8)

    # Formatting
    ax.set_xlabel('Week', fontsize=12, fontweight='bold')
    ax.set_ylabel('Average Duration (minutes)', fontsize=12, fontweight='bold')
    ax.set_title(f'Top {top_n} Slowest Jobs - Duration Over Time',
                 fontsize=14, fontweight='bold', pad=20)

    # Rotate x-axis labels
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

    # Add grid
    ax.grid(True, alpha=0.3, linestyle='--')

    # Add legend below the plot - adjust columns based on number of jobs
    ncol = min(3, max(2, top_n // 5))  # 2-3 columns depending on number of jobs
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15),
              ncol=ncol, fontsize=9, framealpha=0.9)

    # Adjust layout to make room for legend below
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.2)

    # Save the plot
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nPlot saved to: {output_file}")

    # Print summary statistics
    print("\n=== Summary Statistics ===")
    print(f"Number of weeks analyzed: {len(set(w for durations in job_durations.values() for w, _, _ in durations))}")
    print(f"Total unique jobs: {len(job_durations)}")
    print(f"Jobs plotted: {len(slowest_job_names)}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Plot workflow run durations or job durations from gh-workflow-stats JSON output"
    )
    parser.add_argument(
        'input_files',
        nargs='*',
        default=['workflow-stats.json'],
        help='Path(s) to workflow-stats JSON or job-stats JSON file(s) (default: workflow-stats.json)'
    )
    parser.add_argument(
        '-o', '--output',
        default='workflow_durations.png',
        help='Output file for the plot (default: workflow_durations.png or job_durations.png for --jobs mode)'
    )
    parser.add_argument(
        '-b', '--bucket-days',
        type=int,
        default=1,
        help='Number of days to group data by (default: 1 for daily aggregation) - only for workflow mode'
    )
    parser.add_argument(
        '-j', '--jobs',
        action='store_true',
        help='Analyze job statistics instead of workflow runs'
    )
    parser.add_argument(
        '-n', '--top-n',
        type=int,
        default=10,
        help='Number of top slowest jobs to plot (default: 10) - only for job mode'
    )

    args = parser.parse_args()

    # Handle default case
    if not args.input_files:
        if args.jobs:
            args.input_files = ['job-stats.json']
        else:
            args.input_files = ['workflow-stats.json']

    # Set default output filename based on mode
    if args.output == 'workflow_durations.png' and args.jobs:
        args.output = 'job_durations.png'

    if args.jobs:
        # Job statistics mode
        print(f"Loading job stats from {len(args.input_files)} file(s)...")
        data_list = load_job_stats(args.input_files)

        print("Extracting job durations...")
        job_durations = extract_job_durations(data_list)

        if job_durations:
            print("Creating plot...")
            plot_job_durations(job_durations, args.output, args.top_n)
        else:
            print("No job data to plot!", file=sys.stderr)
            sys.exit(1)
    else:
        # Workflow statistics mode (original behavior)
        print(f"Loading workflow stats from {len(args.input_files)} file(s)...")
        data_list = load_workflow_stats(args.input_files)

        print("Extracting successful runs...")
        runs, total_runs, all_runs_for_rate = extract_successful_runs(data_list)

        print(f"Found {len(runs)} successful initial runs (run_attempt=1, after deduplication)")

        if runs:
            print("Creating plot...")
            if args.bucket_days != 1:
                print(f"Grouping data into {args.bucket_days}-day buckets...")
            plot_durations(runs, total_runs, all_runs_for_rate, args.output, args.bucket_days)
        else:
            print("No successful runs to plot!", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
