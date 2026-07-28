import math
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from ffmpeg import FFmpeg, FFmpegError
from ffbatch.myconsole import MyConsole
from .job import Job
from .jobargs import JobArgs


class JobFactory:
    """Parse the input parameters and extract a list of jobs to run.

    Use the command line arguments provided by the user and the information in the chosen preset.
    A job is created for every file found. Every job contains all the required information to run. 
    """


    def __init__(self, console : MyConsole, job_args : JobArgs, o : str, r : bool, f : bool, F : bool, i : list[str], **kwargs):
        self._console = console
        self._job_args = job_args
        self._arg_output = o
        self._arg_recursive = r
        self._arg_force = f
        self._arg_input = i
        self._arg_file_input = F


    def get_jobs_list(self) -> list[Job]:
        """Scan the input files and directories and for each file create a job to run

        Returns:
            list[Job]: List of jobs to run
        """

        # Generate a list of "raw" jobs, only input, output and ffmpeg_args are set
        if self._arg_file_input:
            jobs = self._get_raw_jobs_text_files()
        else:
            jobs = self._get_raw_jobs()

        # Get metadata about the input video and complete the jobs
        for job in jobs:
            job.action = Job.Action.Skip

            # Get video file duration
            try:
                job.duration_sec = self.get_video_duration_in_sec(job.input_path)
            except FFmpegError as exception:
                self._console.verbose('\nException when retrieving metadata:')
                self._console.verbose(f'- Message from ffmpeg: "{exception.message}"')
                self._console.verbose(f'- Arguments given to ffmpeg:' + str(exception.arguments))
                job.error_msg = exception.message.split(':', 1)[1].lstrip()
                continue

            # Decide action to take on target
            if not job.output_path.exists():
                job.action = Job.Action.Create

            elif self._arg_force:
                job.action = Job.Action.Overwrite

        return jobs


    def _get_raw_jobs(self) -> list[Job]:
        jobs = []

        self._console.verbose('\nGenerating job list:')

        for path_str in self._arg_input:
            path = Path(path_str)

            if path.is_file():
                self._console.verbose(f'  Adding file: [{path_str}]')
                jobs.append(self._new_job(path.parents[0], path))

            elif path.is_dir():
                self._console.verbose(f'  Adding directory: [{path_str}]')
                ip = self._get_list_off_files_in_directory(path)

                for i in ip:
                    jobs.append(self._new_job(path, i))

            else:
                self._console.error(f'input path "{path_str}" does not exist')

        return jobs


    def _get_raw_jobs_text_files(self) -> list[Job]:
        """Parse the input files and retrieve a list of jobs.
        The input files are expected to be text files with a paths separated by new lines.

        Returns:
            list[Job]: Raw jobs, only the input output path and ffmpeg_args is set
        """
        jobs = []

        self._console.verbose('\nGenerating job list:')

        for file_str in self._arg_input:
            self._console.verbose(f'  Reading input file: [{file_str}]')
            with Path(file_str).open('r', encoding="utf-8") as file:
                for n, line in enumerate(file):
                    line = line.strip(' \n\r')

                    if line == '':
                        continue

                    self._console.verbose(f'  line: [{line}]')

                    # Check that the path exists
                    path = Path(line)
                    if (not path.exists()):
                        raise ValueError(f'File path not found when evaluating input file "{file_str}", line {n + 1}: [{line}]')

                    jobs.append(self._new_job(path, i))

        return jobs


    def _new_job(self, input_dir : Path, input_path : Path) -> Job:
        op = Path(self._arg_output).joinpath(input_path.relative_to(input_dir)).with_suffix(self._job_args.out_file_ext)
        job = Job(input_path, op, self._job_args)
        self._console.verbose(f'  generated job: {job}')
        return job


    def _get_list_off_files_in_directory(self, root_path : Path) -> list[Path]:
        file_list = []
        rd = root_path.glob('*')

        # Test every entry to see if it is a file or a directory
        for x in rd:
            if x.is_file():
                self._console.verbose(f'  Adding file: [{x}]')
                file_list.append(x)

            elif x.is_dir() and self._arg_recursive:
                self._console.verbose(f'  Adding directory: [{x}]')
                file_list.extend(self._get_list_off_files_in_directory(x))

        return file_list


    def get_video_duration_in_sec(self, path : Path) -> float:
        ffprobe = FFmpeg(executable="ffprobe").input(
            str(path),
            options={"v": "error", "show_entries": "format=duration"}
        )

        probe_out = str(ffprobe.execute()).split('duration=', 1)[1].split('[/FORMAT]', 1)[0].strip('\\n').strip('\\r')

        return float(probe_out)
