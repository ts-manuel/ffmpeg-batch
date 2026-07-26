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
from ffbatch.preset import Preset
from ffbatch.targets import Targets


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

    args = parser.parse_args()

    # Register interrup handler for ctrl + c
    signal.signal(signal.SIGINT, signal_handler)

    console = MyConsole()
    console.verbose_enabled = args.v

    console.verbose('\nInput parameters:')
    console.verbose(f'  args.input : {args.i}')
    console.verbose(f'  args.input : {args.o}')
    console.verbose(f'  Recursive .: {args.r}')
    console.verbose(f'  verbose ...: {console.verbose_enabled}')
    console.verbose(f'  Force .....: {args.f}')
    console.verbose(f'  Preset ....: {args.p}')

    # Check if output path exists
    output_directory = Path(args.o)
    if not output_directory.is_dir():
        console.error(f'output path "{args.o}" does not exist, create output path before running the script')

    # Assert that a valid preset is specified and get its entry by name
    try:
        preset = Preset(console, args.p)
    except ValueError:
        console.print('use the -p option to select one of the following presets:')
        for i, p in enumerate(Preset.get_available_preset_names()):
            console.print(f'[{i + 1}]: {p}')
        console.print(f'you can add other presets by editing the file "{Preset.get_user_presets_file_path()}"')
        sys.exit(1)

    console.verbose(f'\nLoaded preset: {preset}')

    # Generate list of target files to convert
    targets = Targets(console, args.i, args.o, args.r, args.f, preset)

    if targets.count == 0:
        console.error('no valid input file specified')

    # Print the list of files to be converted and ask if OK to continue
    targets.print()

    if ask_for_confirmation(console, targets.files_to_create, targets.files_to_overwrite, targets.files_to_skip):
        # Do the conversion
        doConvert(console, targets, preset)


def signal_handler(sig, frame):
    print('\nConversion terminated by USER')
    sys.exit(0)


def ask_for_confirmation(console : MyConsole, files_to_create : int, files_to_overwrite : int, files_to_skip : int) -> bool:
    number_of_digits = math.ceil(math.log10(max(files_to_create, files_to_overwrite, files_to_skip)))
    files_to_process = files_to_create + files_to_overwrite

    console.print(f'\nCreating .. : {files_to_create:{number_of_digits}} files')
    console.print(f'Overwriting : {files_to_overwrite:{number_of_digits}} files')
    console.print(f'Skipping .. : {files_to_skip:{number_of_digits}} files')
    console.print(f'\nTotal files to process {files_to_process}')

    if files_to_process == 0:
        return False

    # Ask for confirmation and whait for valid response
    result = ''
    while result != 'y' and result != 'n':
        result = console.input('Do you want to continue? [Y/n] ')
    console.print()

    return result == 'y'


def doConvert(console : MyConsole, targets : Targets, preset : Preset):
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
        total_time_sec = sum([x.duration_sec for x in targets if x.action != Targets.Target.Action.Skip])
        overall_task_id = overall_progress.add_task("[red]Progress...", total=total_time_sec)
        conv_task_id = conv_progress.add_task(f'[yellow] ... ')
        files_to_process = targets.files_to_create + targets.files_to_overwrite
        target_index = 0

        for target in targets:

            if target.action == Targets.Target.Action.Skip:
                continue

            # Create output directory if doesn't exist
            target.output_path.parent.mkdir(parents=True, exist_ok=True)

            index_of_total_str = f'{target_index} of {files_to_process}'.rjust(11)
            conv_progress.update(conv_task_id, completed=0, description=f'[yellow]{index_of_total_str}', total=target.duration_sec, fps=0, speed=0, size=0, file_name=target.output_path.name)

            try:
                ffmpeg = (
                    FFmpeg()
                    .option("y")
                    .input(str(target.input_path))
                    .output(
                        str(target.output_path),
                        options=preset.ffmpeg_args
                    )
                )

                @ffmpeg.on("progress")
                def on_progress(progress: Progress):
                    conv_progress.update(conv_task_id, completed=progress.time.seconds, fps=progress.fps, speed=progress.speed, size=HurryFileSize(progress.size))
                    overall_progress.update(overall_task_id, completed=accumulated_time + progress.time.seconds)

                @ffmpeg.on("completed")
                def on_completed():
                    conv_progress.update(conv_task_id, completed=target.duration_sec)
                    nonlocal accumulated_time
                    accumulated_time += target.duration_sec
                    nonlocal target_index
                    target_index += 1

                console.verbose(f"\nRunning ffmpeg with: {ffmpeg.arguments}")

                ffmpeg.execute()

            except FFmpegerror as exception:
                print("\nAn exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)

        overall_progress.update(overall_task_id, completed=total_time_sec)


if __name__ == "__main__":
   main()