import sys
import signal
import math
import argparse
from pathlib import Path
from ffmpeg import FFmpeg, FFmpegError, Progress
from rich.progress import Progress as RichProgress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.live import Live
from rich.console import Group
from hurry.filesize import size as HurryFileSize
from ffbatch.myconsole import MyConsole
from .presetloader import PresetLoader
from .job import Job, JobFactory


class CustomHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def __init__(self, *args, **kwargs):
        kwargs["max_help_position"] = 30    # default to 24
        super().__init__(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(
       description='Batch precess media files with ffmpeg.',
       formatter_class=CustomHelpFormatter
    )
    parser.add_argument('-r', action='store_true', help='recursive evaluation (include sub directories)')
    parser.add_argument('-f', action='store_true', help='do not skip already existing output files')
    parser.add_argument('-v', action='store_true', help='show debug output on console')
    parser.add_argument('-p', metavar='PRESET', help='preset to use for file conversion')
    parser.add_argument('-i', metavar='INPUT', nargs='+', help='input file paths or directories to be evaluated', required=True)
    parser.add_argument('-o', metavar='OUTPUT', help='output directory where to store converted files', required=True)

    args = vars(parser.parse_args())

    # Register interrupt handler for ctrl + c
    signal.signal(signal.SIGINT, signal_handler)

    console = MyConsole()
    console.verbose_enabled = args['v']

    console.verbose('\nInput parameters:')
    console.verbose(f'  args.input : {args['i']}')
    console.verbose(f'  args.input : {args['o']}')
    console.verbose(f'  Recursive .: {args['r']}')
    console.verbose(f'  verbose ...: {args['v']}')
    console.verbose(f'  Force .....: {args['f']}')
    console.verbose(f'  Preset ....: {args['p']}')

    # Check if output path exists
    output_directory = Path(args['o'])
    if not output_directory.is_dir():
        console.error(f'output path "{args.o}" does not exist, create output path before running the script')

    # Assert that a valid preset is specified and get its entry by name
    presetLoader = PresetLoader(console)
    try:
        job_args = presetLoader.get_preset_by_name(args['p'])
    except ValueError:
        console.print('use the -p option to select one of the following presets:')
        for i, p in enumerate(PresetLoader.get_available_preset_names()):
            console.print(f'[{i + 1}]: {p}')
        console.print(f'you can add other presets by editing the file "{PresetLoader.get_user_presets_file_path()}"')
        sys.exit(1)
    console.verbose(f'\nLoaded preset: {job_args}')

    # Generate list of target files to convert
    jobFactory = JobFactory(console, job_args, **args)
    jobs = jobFactory.get_jobs_list()

    if jobs.count == 0:
        console.error('no valid input file specified')

    # Print the list of files to be converted and ask if OK to continue
    print_job_list(console, jobs)
    if len(jobs) == 0:
        return

    if ask_for_confirmation(console):
        # Do the conversion
        doConvert(console, jobs)


def signal_handler(sig, frame):
    print('\nConversion terminated by USER')
    sys.exit(0)


def print_job_list(console : MyConsole, jobs : list[Job]):
    number_of_digits = math.ceil(math.log10(len(jobs)))
    files_to_create = 0
    files_to_overwrite = 0
    files_to_skip = 0

    color_set = ['[green]', '[yellow]', '[red]']
    color_clr = ['[/green]', '[/yellow]', '[/red]']

    console.print('\nOutput files:')

    # Print list of files to be converted
    for i, job in enumerate(jobs):

        if job.output_path.is_absolute():
            full_out_path = str(job.output_path)
        else:
            full_out_path = str(Path.cwd().joinpath(job.output_path))

        console.print(f'[{i:0{number_of_digits}}]: {color_set[job.action.value]}{job.action.name:{9}} {color_clr[job.action.value]} : {full_out_path}')

        if job.error_msg != "":
            console.print(f'{' ':{4 + number_of_digits}}[red]{job.error_msg}')

        match job.action:
            case Job.Action.Create:
                files_to_create += 1
            case Job.Action.Overwrite:
                files_to_overwrite += 1
            case Job.Action.Skip:
                files_to_skip += 1

    # Print summary
    number_of_digits = math.ceil(math.log10(max(files_to_create, files_to_overwrite, files_to_skip)))
    files_to_process = files_to_create + files_to_overwrite
    console.print(f'\nCreating .. : {files_to_create:{number_of_digits}} files')
    console.print(f'Overwriting : {files_to_overwrite:{number_of_digits}} files')
    console.print(f'Skipping .. : {files_to_skip:{number_of_digits}} files')
    console.print(f'\nTotal files to process {files_to_process}')


def ask_for_confirmation(console : MyConsole) -> bool:

    # Ask for confirmation and wait for valid response
    result = ''
    while result != 'y' and result != 'n':
        result = console.input('Do you want to continue? [Y/n] ')
    console.print()

    return result == 'y'


def doConvert(console : MyConsole, jobs : list[Job]):
    conv_progress = RichProgress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        TextColumn("[yellow]fps: {task.fields[fps]}"),
        TextColumn("[yellow]size: {task.fields[size]}"),
        TextColumn("[yellow]speed: {task.fields[speed]}x"),
        TextColumn("[light_sky_blue1] {task.fields[file_name]}"),
        transient=True
    )

    overall_progress = RichProgress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        transient=True
    )

    group = Group(
        conv_progress,
        overall_progress
    )

    live = Live(group, transient=True)

    with live:
        accumulated_time = 0
        total_time_sec = sum([x.duration_sec for x in jobs if x.action != Job.Action.Skip])
        overall_task_id = overall_progress.add_task("[red]Progress...", total=total_time_sec)
        conv_task_id = conv_progress.add_task(f'[yellow] ... ')
        files_to_process = len([x for x in jobs if x.action == Job.Action.Create or x.action == Job.Action.Override])
        job_index = 0

        for job in jobs:

            if job.action == Job.Action.Skip:
                continue

            # Create output directory if doesn't exist
            job.output_path.parent.mkdir(parents=True, exist_ok=True)

            index_of_total_str = f'{job_index} of {files_to_process}'.rjust(11)
            conv_progress.update(conv_task_id, completed=0, description=f'[yellow]{index_of_total_str}', total=job.duration_sec, fps=0, speed=0, size=0, file_name=job.output_path.name)

            try:
                ffmpeg = (
                    FFmpeg()
                    .option("y")
                    .input(str(job.input_path))
                    .output(
                        str(job.output_path),
                        options=job.ffmpeg_args
                    )
                )

                @ffmpeg.on("progress")
                def on_progress(progress: Progress):
                    conv_progress.update(conv_task_id, completed=progress.time.seconds, fps=progress.fps, speed=progress.speed, size=HurryFileSize(progress.size))
                    overall_progress.update(overall_task_id, completed=accumulated_time + progress.time.seconds)

                @ffmpeg.on("completed")
                def on_completed():
                    conv_progress.update(conv_task_id, completed=job.duration_sec)
                    nonlocal accumulated_time
                    accumulated_time += job.duration_sec
                    nonlocal job_index
                    job_index += 1

                console.verbose(f"\nRunning ffmpeg with: {ffmpeg.arguments}")

                ffmpeg.execute()

            except FFmpegError as exception:
                print("\nAn exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)

        overall_progress.update(overall_task_id, completed=total_time_sec)


if __name__ == "__main__":
   main()