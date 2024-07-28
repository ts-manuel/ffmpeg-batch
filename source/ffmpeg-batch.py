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
from rich.console import Group
from hurry.filesize import size as HurryFileSize
from termcolor import colored


# Global variables
g_verbose = False
G_PREASETS_FILE = 'presets.json'


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
            print_available_presets()
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


    def __repr__(self):
        return (f'[{self.name}]\n' +
                f'  out_file_ext : {self.out_file_ext}\n' +
                f'  ffmpeg_args .: {self.ffmpeg_args}')


@dataclass
class Target:
    input_path: Path
    output_path: Path
    do_convert: bool = True


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
    parser.add_argument('-i', metavar='INPUT', nargs='+', help='input file paths or directories to be evaluated')
    parser.add_argument('-o', metavar='OUTPUT', help='output directory where to store converted files')

    args = parser.parse_args()

    # Register interrup handler for ctrl + c
    signal.signal(signal.SIGINT, signal_handler)

    global g_verbose
    g_verbose = args.v

    vprint('\nInput parameters:')
    vprint(f'  args.input : {args.i}')
    vprint(f'  args.input : {args.o}')
    vprint(f'  Recursive .: {args.r}')
    vprint(f'  Verbose ...: {g_verbose}')
    vprint(f'  Force .....: {args.f}')
    vprint(f'  Preset ....: {args.p}')

    # Check if output path exists
    output_directory = Path(args.o)
    if not output_directory.is_dir():
        error(f'output path "{args.o}" does not exist, create output path before running the script')

    # Assert that a valid preset is specified and get its entry by name
    #preset = assert_and_get_valid_preset(args.p)
    preset = Preset(args.p)
    vprint(f'\nLoaded preset: {preset}')

    # Generate list of target files to convert
    targetList = generate_target_list(args.i, args.o, args.r, args.f, preset)

    if len(targetList) == 0:
        error('no valid input file specified')

    # Print the list of files to be converted and ask if OK to continue
    if print_files_to_convert_and_ask_for_confirmation(targetList):
        # Do the conversion
        doConvert(targetList, preset)


def signal_handler(sig, frame):
    print('\nConversion terminated by USER')
    sys.exit(0)


def assert_and_get_valid_preset(preset_name : str) -> dict:
    with open(G_PREASETS_FILE, 'r') as f:
        presets = json.load(f)

    # Check if the preset argument is pecified ad is a valid preset name
    if preset_name == None or not preset_name in presets:
        error('no valid preset specified, use the -p option to slect one of the following presets:', False)
        print_available_presets()
        sys.exit(1)

    # Check if the preset contains the required key fields
    preset = presets[preset_name]
    keywords_to_ceck = ['output_file_ext', 'ffmpeg_args']
    key_not_found = False

    for k in keywords_to_ceck:
        if not k in preset:
            error(f'wrong sintax in preset file: {G_PREASETS_FILE}, keyword "{k}" not set for preset "{preset_name}"', False)
            key_not_found = True

    if key_not_found:
        sys.exit()

    return preset


def print_available_presets():
    with open(G_PREASETS_FILE, 'r') as f:
        presets = json.load(f)

    for p in presets:
        print(f' - {p}')


def generate_target_list(input_list : list[str], output : str, recursive : bool, force : bool, preset : Preset) -> list[Target]:
    target_list = []

    vprint('\nGenerating target list:')

    def generate_target(input_dir : Path, output_dir: Path, input_path : Path, file_ext : str, force : bool) -> Target:
            op = output_dir.joinpath(input_path.relative_to(input_dir)).with_suffix(file_ext)
            dc = not op.exists() or force
            tg = Target(input_path, op, dc)
            vprint(f'  generated target: {tg}')
            return tg

    for in_path in input_list:
        pt = Path(in_path)

        if pt.is_file():
            vprint(f'  Adding file: [{in_path}]')
            target_list.append(generate_target(pt.parents[0], Path(output), pt, preset.out_file_ext, force))

        elif pt.is_dir():
            vprint(f'  Adding directory: [{in_path}]')
            ip = get_list_off_files_in_directory(pt, recursive)

            for i in ip:
                target_list.append(generate_target(pt, Path(output), i, preset.out_file_ext, force))

        else:
            error(f'input path "{in_path}" does not exist')

    return target_list


def get_list_off_files_in_directory(root_path : Path, recursive : bool) -> list[Path]:
    file_list = []
    rd = root_path.glob('*')

    # Test every entry to see if it is a file or a directory
    for x in rd:
        if x.is_file():
            vprint(f'  Adding file: [{x}]')
            file_list.append(x)

        elif x.is_dir() and recursive:
            vprint(f'  Adding directory: [{x}]')
            file_list.extend(get_list_off_files_in_directory(x, recursive))

    return file_list


def print_files_to_convert_and_ask_for_confirmation(target_list : list[Target]) -> bool:
    target_count = len(target_list)
    number_of_digits = math.ceil(math.log10(target_count))
    files_to_convert = 0

    print('\nFiles to be converted:')

    # Print list of files to be converted
    for i in range(target_count):
        tp = target_list[i]
        if tp.do_convert:
            print('[{0:0{n}}]: Input : {1}'.format(files_to_convert, str(tp.input_path), n=number_of_digits))
            print('{0:{n}}Output: {1}'.format(' ', str(tp.output_path),  n=(number_of_digits + 4)))
            files_to_convert = files_to_convert + 1

    print(f'\nConverting {files_to_convert} files')

    # Ask for confirmation and whait for valid response
    result = ''
    while result != 'y' and result != 'n':
        result = input('Do you want to continue? [Y/n] ')
    print()

    return result == 'y'


def doConvert(target_list : list[Target], preset : Preset):
    conv_progress = RichProgress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        TextColumn("[yellow]fps: {task.fields[fps]}"),
        TextColumn("[yellow]size: {task.fields[size]}"),
        TextColumn("[yellow]speed: {task.fields[speed]}x"),
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
        total_time_sec = get_video_list_duratio_in_sec([x.input_path for x in target_list if x.do_convert])
        overall_task_id = overall_progress.add_task("[red]Progress...", total=total_time_sec)
        conv_task_list = []

        for target in target_list:

            # Skip this target if the doConvert flag is not set
            if not target.do_convert:
                continue

            # Create output directory if doesn't exist
            target.output_path.parent.mkdir(parents=True, exist_ok=True)

            duratio_in_sec = get_video_duration_in_sec(target.input_path)

            conv_task_list.append(conv_progress.add_task(f"[yellow]{target.output_path.name}", total=duratio_in_sec, fps=0, speed=0, size=0))

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
                    conv_progress.update(conv_task_list[-1], completed=duratio_in_sec)
                    nonlocal accumulated_time
                    accumulated_time += duratio_in_sec

                vprint(f"\nRunning ffmpeg with: {ffmpeg.arguments}")

                ffmpeg.execute()

            except FFmpegError as exception:
                print("\nAn exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)

        overall_progress.update(overall_task_id, completed=total_time_sec)


def get_video_list_duratio_in_sec(target_list : list[Path]) -> float:
    duration = float(0)

    vprint(f'\nGet video duration for list of {len(target_list)} items:')

    for x in target_list:
        vprint(f'  getting duration for {x}')
        duration += get_video_duration_in_sec(x)

    return duration


def get_video_duration_in_sec(path : Path) -> float:
    ffprobe = FFmpeg(executable="ffprobe").input(
        str(path),
        print_format="json", # ffprobe will output the results in JSON format
        show_streams=None,
    )

    media = json.loads(ffprobe.execute())

    return float(media['streams'][0]['duration'])


def vprint(s = ''):
    if g_verbose: print(s)


def error(message : str, terminate : bool = True):
    sys.stderr.write(
        colored('\nerror:', 'red', attrs=["bold"]) + ' ' + message + '\n'
    )
    if terminate:
        sys.exit(1)


if __name__ == "__main__":
   main()