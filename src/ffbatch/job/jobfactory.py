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


    def __init__(self, console : MyConsole, job_args : JobArgs,
                 o : str, r : bool, f : bool, F : bool, c : bool, R : str | None, i : list[str], **kwargs):

        # Check that the output directory exists
        self._arg_output = Path(o)
        if not self._arg_output.is_dir():
            raise ValueError(f'output directory does not exist: [{o}]')

        self._arg_relative = None
        if R is not None:
            self._arg_relative = Path(R)
            if not self._arg_relative.is_dir():
                raise ValueError(f'the RELATIVE argument must be a valid directory: [{R}]')

        self._console = console
        self._job_args = job_args
        self._arg_recursive = r     # Search input folders recursively for files to precess
        self._arg_force = f         # Force overwrite of existing files
        self._arg_input = i         # Input file paths as list[str] (can be relative or absolute)
        self._arg_file_input = F    # Interpret input as text file
        self._arg_clone = c         # Clone the input folder structure to the output folder


    def get_jobs_list(self) -> list[Job]:
        """Scan the input files and directories and for each file create a job to run

        Returns:
            list[Job]: List of jobs to run
        """

        # Generate a list of "raw" jobs, only input, output and ffmpeg_args are set
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
        """Parse input file paths and build a list of jobs

        The only field populated by this function are:
            input_path, output_path, args

        Returns:
            list[Job]: List of jobs
        """
        jobs = []

        self._console.verbose('\nGenerating job list:')

        # Loop over all the user provided input paths
        for input_path_str in self._arg_input:
            input_path = Path(input_path_str)
            self._console.verbose(f'parsing path: [{input_path}]')

            if input_path.is_file():
                jobs.extend(self._get_raw_jobs_from_file(input_path, None))

            elif input_path.is_dir():
                jobs.extend(self._get_raw_jobs_from_directory(input_path, input_path))

            else:
                self._console.error(f'input path "{input_path}" does not exist')

        return jobs


    def _get_raw_jobs_from_directory(self, dir_path : Path, root_path : None | Path) -> list[Job]:
        """Scan the directory and parse all the files

        Args:
            dir_path (Path):            Directory to search
            root_path (None | Path):    Parent directory

        Returns:
            list[Job]: List of jobs
        """
        jobs = []

        if self._arg_recursive:
            rd = dir_path.rglob('*')
        else:
            rd = dir_path.glob('*')

        for x in rd:
            if x.is_file():
                jobs.extend(self._get_raw_jobs_from_file(x, root_path))

        return jobs


    def _get_raw_jobs_from_file(self, file_path : Path, root_path : None | Path) -> list[Job]:
        """Parse input file path and construct a raw job

        If the -F options is set file_path is read as a text file,
        the expected content is file paths separated by new lines.

        Args:
            file_path (Path):           Path to evaluate
            root_oath (None | Path):    Parent directory

        Returns:
            list[Job]: List of raw jobs
        """
        jobs = []

        # If the -F flag is set interpret file_path as a text file
        if self._arg_file_input:
            self._console.verbose(f'  Reading input file: [{file_path}]')
            with file_path.open('r', encoding="utf-8") as file:
                for n, line in enumerate(file):
                    line = line.strip(' \n\r')

                    if line == '':
                        continue

                    self._console.verbose(f'  line: [{line}]')

                    # Check that the path exists
                    path = Path(line)
                    if (not path.exists()):
                        raise ValueError(f'File path not found when evaluating input file "{file_path}", line {n + 1}: [{line}]')

                    self._console.verbose(f'    appending file [{path}]')
                    jobs.append(self._new_raw_job(path, None))
        else:
            self._console.verbose(f'    appending file [{file_path}]')
            jobs.append(self._new_raw_job(file_path, root_path))

        return jobs


    def _new_raw_job(self, input_path : Path, root_path : None | Path) -> Job:
        """Construct a raw job
        
        If the -c option is set the output path is computed by prepending the input path relative to the input directory with the output directory.
        If not set the input files are stripped of any parent directory before been prepended with the output directory.

        Args:
            input_path (Path):          Path to the input file
            root_path (None | Path):    Path to the parent directory

        Returns:
            Job: New job with input_path, output_path and args set
        """
        if self._arg_relative is not None:
            root_path = self._arg_relative

        if self._arg_clone and root_path is not None:
            output_path = self._arg_output.joinpath(input_path.relative_to(root_path))
            self._console.verbose(f'    cloning output path, input: [{input_path}], input_dir: [{root_path}] -> [{output_path}]')
        else:
            output_path = self._arg_output.joinpath(input_path.name)

        # Set file extension
        output_path = output_path.with_suffix(self._job_args.out_file_ext)

        return Job(input_path, output_path, self._job_args)


    def get_video_duration_in_sec(self, path : Path) -> float:
        ffprobe = FFmpeg(executable="ffprobe").input(
            str(path),
            options={"v": "error", "show_entries": "format=duration"}
        )

        probe_out = str(ffprobe.execute()).split('duration=', 1)[1].split('[/FORMAT]', 1)[0].strip('\\n').strip('\\r')

        return float(probe_out)
