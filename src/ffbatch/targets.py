import math
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from ffmpeg import FFmpeg, FFmpegError
from ffbatch.myconsole import MyConsole
from ffbatch.preset import Preset


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


    def __init__(self, console : MyConsole, input_list : list[str], output : str, recursive : bool, force : bool, preset : Preset):
        # Scan the input directories / files and generate the list Targets initialized with input output path and exists flaf
        self._console = console
        self._initialize_file_paths(input_list, output, recursive, preset)
        self.files_to_create = 0
        self.files_to_overwrite = 0

        # Get metadata about the input files
        for x in self._data:
            x.action = Targets.Target.Action.Skip

            try:
                x.duration_sec = self.get_video_duration_in_sec(x.input_path)
            except FFmpegError as exception:
                self._console.verbose('\nException when retriving metadata:')
                self._console.verbose(f'- Message from ffmpeg: "{exception.message}"')
                self._console.verbose(f'- Arguments to execute ffmpeg:' + str(exception.arguments))
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

        self._console.verbose('\nGenerating target list:')

        for in_path in input_list:
            pt = Path(in_path)

            if pt.is_file():
                self._console.verbose(f'  Adding file: [{in_path}]')
                self._data.append(self._generate_target(pt.parents[0], Path(output), pt, preset.out_file_ext))

            elif pt.is_dir():
                self._console.verbose(f'  Adding directory: [{in_path}]')
                ip = self._get_list_off_files_in_directory(pt, recursive)

                for i in ip:
                    self._data.append(self._generate_target(pt, Path(output), i, preset.out_file_ext))

            else:
                self._console.error(f'input path "{in_path}" does not exist')


    def _generate_target(self, input_dir : Path, output_dir: Path, input_path : Path, file_ext : str) -> Target:
        op = output_dir.joinpath(input_path.relative_to(input_dir)).with_suffix(file_ext)
        tg = self.Target(input_path, op, op.exists())
        self._console.verbose(f'  generated target: {tg}')
        return tg


    def _get_list_off_files_in_directory(self, root_path : Path, recursive : bool) -> list[Path]:
        file_list = []
        rd = root_path.glob('*')

        # Test every entry to see if it is a file or a directory
        for x in rd:
            if x.is_file():
                self._console.verbose(f'  Adding file: [{x}]')
                file_list.append(x)

            elif x.is_dir() and recursive:
                self._console.verbose(f'  Adding directory: [{x}]')
                file_list.extend(self._get_list_off_files_in_directory(x, recursive))

        return file_list


    def get_video_duration_in_sec(self, path : Path) -> float:
        ffprobe = FFmpeg(executable="ffprobe").input(
            str(path),
            options={"v": "error", "show_entries": "format=duration"}
        )

        probe_out = str(ffprobe.execute()).split('duration=', 1)[1].split('[/FORMAT]', 1)[0].strip('\\n').strip('\\r')

        return float(probe_out)


    def __getitem__(self, item):
        return self._data[item]


    def print(self):
        number_of_digits = math.ceil(math.log10(len(self._data)))
        files_to_convert = 0

        color_set = ['[green]', '[yellow]', '[red]']
        color_clr = ['[/green]', '[/yellow]', '[/red]']

        self._console.print('\nOutput files:')

        # Print list of files to be converted
        for i, tp in enumerate(self):

            if tp.output_path.is_absolute():
                full_out_path = str(tp.output_path)
            else:
                full_out_path = str(Path.cwd().joinpath(tp.output_path))

            self._console.print(f'[{i:0{number_of_digits}}]: {color_set[tp.action.value]}{tp.action.name:{9}} {color_clr[tp.action.value]} : {full_out_path}')

            if tp.action == Targets.Target.Action.Skip:
                self._console.print(f'{' ':{4 + number_of_digits}}[red]{tp.error_msg}')

            if tp.action != Targets.Target.Action.Skip:
                files_to_convert += 1