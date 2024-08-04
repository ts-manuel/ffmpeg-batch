import sys
import signal
import math
import argparse
import json
from pathlib import Path
from dataclasses import dataclass
from ffmpeg import FFmpeg, FFmpegError, Progress
from rich.progress import Progress as RichProgress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, TimeElapsedColumn
from rich.live import Live
from rich.console import Group, Console
from hurry.filesize import size as HurryFileSize
from enum import Enum


# Global variables
g_verbose = False
G_PREASETS_FILE = 'presets.json'
console = Console(highlight=False)


class Preset:
    name : str
    out_file_ext : str
    ffmpeg_args : dict

    def __init__(self, name: str):
        with open(G_PREASETS_FILE, 'r') as f:
            self._presets = json.load(f)

        # Check if the preset argument is pecified ad is a valid preset name
        if name == None or not name in self._presets:
            error('no valid preset specified, use the -p option to slect one of the following presets:', False)
            self._print_available_presets()
            sys.exit(1)

        self.name = name
        self._preset = self._presets[name]
        self._preset_name = name

        # Check if the preset contains the required key fields
        self.out_file_ext = self._try_parse_keyword('output_file_ext')
        self.ffmpeg_args = self._try_parse_keyword('ffmpeg_args')


    def _try_parse_keyword(self, key : str):
        if not key in self._preset:
            error(f'wrong sintax in preset file: {G_PREASETS_FILE}, keyword "{key}" not set for preset "{self.name}"')
        return self._preset[key]


    def _print_available_presets(self):
        with open(G_PREASETS_FILE, 'r') as f:
            presets = json.load(f)

        for p in presets:
            print(f' - {p}')


    def __repr__(self):
        return (f'[{self.name}]\n' +
                f'  out_file_ext : {self.out_file_ext}\n' +
                f'  ffmpeg_args .: {self.ffmpeg_args}')


class Targets:

    @dataclass
    class Target:
        class Action(Enum):
            Create = 0
            Overwrite = 1
            Skip = 2


        input_path: Path
        output_path: Path
        output_exists: bool
        error_msg : str = ''
        action : Action = Action.Skip
        duration_sec : float = 0
        files_to_create : int = 0
        files_to_overwrite : int = 0
        files_to_skip : int = 0


    @property
    def count(self):
        return len(self._data)


    _data : list[Target] = []


    def __init__(self, input_list : list[str], output : str, recursive : bool, force : bool, preset : Preset):
        # Scan the input directories / files and generate the list Targets initialized with input output path and exists flaf
        self._initialize_file_paths(input_list, output, recursive, preset)
        self.files_to_create = 0
        self.files_to_overwrite = 0

        # Get metadata about the input files
        for x in self._data:
            x.action = Targets.Target.Action.Skip

            try:
                x.duration_sec = self.get_video_duration_in_sec(x.input_path)
            except FFmpegError as exception:
                verbose('\nException when retriving metadata:')
                verbose(f'- Message from ffmpeg: "{exception.message}"')
                verbose(f'- Arguments to execute ffmpeg:' + str(exception.arguments))
                x.error_msg = exception.message.split(':', 1)[1].lstrip()
                continue

            # Decide action to take on target
            if not x.output_exists:
                x.action = Targets.Target.Action.Create
                self.files_to_create += 1
                continue

            if x.output_exists and force:
                x.action = Targets.Target.Action.Overwrite
                self.files_to_overwrite += 1

        self.files_to_skip = self.count - self.files_to_create - self.files_to_overwrite


    def _initialize_file_paths(self, input_list : list[str], output : str, recursive : bool, preset : Preset) -> list[Target]:
        self._data = []

        verbose('\nGenerating target list:')

        for in_path in input_list:
            pt = Path(in_path)

            if pt.is_file():
                verbose(f'  Adding file: [{in_path}]')
                self._data.append(self._generate_target(pt.parents[0], Path(output), pt, preset.out_file_ext))

            elif pt.is_dir():
                verbose(f'  Adding directory: [{in_path}]')
                ip = self._get_list_off_files_in_directory(pt, recursive)

                for i in ip:
                    self._data.append(self._generate_target(pt, Path(output), i, preset.out_file_ext))

            else:
                error(f'input path "{in_path}" does not exist')


    def _generate_target(self, input_dir : Path, output_dir: Path, input_path : Path, file_ext : str) -> Target:
        op = output_dir.joinpath(input_path.relative_to(input_dir)).with_suffix(file_ext)
        tg = self.Target(input_path, op, op.exists())
        verbose(f'  generated target: {tg}')
        return tg


    def _get_list_off_files_in_directory(self, root_path : Path, recursive : bool) -> list[Path]:
        file_list = []
        rd = root_path.glob('*')

        # Test every entry to see if it is a file or a directory
        for x in rd:
            if x.is_file():
                verbose(f'  Adding file: [{x}]')
                file_list.append(x)

            elif x.is_dir() and recursive:
                verbose(f'  Adding directory: [{x}]')
                file_list.extend(self._get_list_off_files_in_directory(x, recursive))

        return file_list


    def get_video_duration_in_sec(self, path : Path) -> float:
        ffprobe = FFmpeg(executable="ffprobe").input(
            str(path),
            print_format="json", # ffprobe will output the results in JSON format
            show_streams=None,
        )

        media = json.loads(ffprobe.execute())

        return float(media['streams'][0]['duration'])


    def __getitem__(self, item):
        return self._data[item]


    def print(self, console : Console):
        number_of_digits = math.ceil(math.log10(len(self._data)))
        files_to_convert = 0

        color_set = ['[green]', '[yellow]', '[red]']
        color_clr = ['[/green]', '[/yellow]', '[/red]']

        console.print('\nInput files:')

        # Print list of files to be converted
        for i, tp in enumerate(self):

            console.print(f'[{i:0{number_of_digits}}]: {color_set[tp.action.value]}{tp.action.name:{9}} {color_clr[tp.action.value]} : {str(tp.input_path)}')

            if tp.action == Targets.Target.Action.Skip:
                console.print(f'{' ':{4 + number_of_digits}}[red]{tp.error_msg}')

            if tp.action != Targets.Target.Action.Skip:
                files_to_convert += 1


class CustomHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def __init__(self, *args, **kwargs):
        kwargs["max_help_position"] = 30    # default to 24
        super().__init__(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(
       description='Wrapper around ffmpeg to process files in batch and add presets.',
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

    global g_verbose
    g_verbose = args.v

    verbose('\nInput parameters:')
    verbose(f'  args.input : {args.i}')
    verbose(f'  args.input : {args.o}')
    verbose(f'  Recursive .: {args.r}')
    verbose(f'  Verbose ...: {g_verbose}')
    verbose(f'  Force .....: {args.f}')
    verbose(f'  Preset ....: {args.p}')

    # Check if output path exists
    output_directory = Path(args.o)
    if not output_directory.is_dir():
        error(f'output path "{args.o}" does not exist, create output path before running the script')

    # Assert that a valid preset is specified and get its entry by name
    preset = Preset(args.p)
    verbose(f'\nLoaded preset: {preset}')

    # Generate list of target files to convert
    targets = Targets(args.i, args.o, args.r, args.f, preset)

    if targets.count == 0:
        error('no valid input file specified')

    # Print the list of files to be converted and ask if OK to continue
    targets.print(console)

    if ask_for_confirmation(targets.files_to_create, targets.files_to_overwrite, targets.files_to_skip):
        # Do the conversion
        doConvert(targets, preset)


def signal_handler(sig, frame):
    print('\nConversion terminated by USER')
    sys.exit(0)


def ask_for_confirmation(files_to_create : int, files_to_overwrite : int, files_to_skip : int) -> bool:
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


def doConvert(targets : Targets, preset : Preset):
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

    live = Live(group)

    with live:
        accumulated_time = 0
        total_time_sec = sum([x.duration_sec for x in targets if x.action != Targets.Target.Action.Skip])
        overall_task_id = overall_progress.add_task("[red]Progress...", total=total_time_sec)
        conv_task_list = []
        files_to_process = targets.files_to_create + targets.files_to_overwrite
        target_index = 0

        for target in targets:

            if target.action == Targets.Target.Action.Skip:
                continue

            # Create output directory if doesn't exist
            target.output_path.parent.mkdir(parents=True, exist_ok=True)

            index_of_total_str = f'{target_index} of {files_to_process}'.rjust(11)
            conv_task_list.append(conv_progress.add_task(f'[yellow]{index_of_total_str}', total=target.duration_sec, fps=0, speed=0, size=0, file_name=target.output_path.name))

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
                    conv_progress.update(conv_task_list[-1], completed=progress.time.seconds, fps=progress.fps, speed=progress.speed, size=HurryFileSize(progress.size))
                    overall_progress.update(overall_task_id, completed=accumulated_time + progress.time.seconds)

                @ffmpeg.on("completed")
                def on_completed():
                    conv_progress.update(conv_task_list[-1], completed=target.duration_sec)
                    nonlocal accumulated_time
                    accumulated_time += target.duration_sec
                    nonlocal target_index
                    target_index += 1

                verbose(f"\nRunning ffmpeg with: {ffmpeg.arguments}")

                ffmpeg.execute()

            except FFmpegError as exception:
                print("\nAn exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)

        overall_progress.update(overall_task_id, completed=total_time_sec)


def verbose(s = ''):
    if not g_verbose:
        return

    console.print(s, style='bright_black')


def error(message : str, terminate : bool = True):
    console.print(f'\n[bold red]error[/bold red]: {message}')
    if terminate:
        sys.exit(1)


if __name__ == "__main__":
   main()