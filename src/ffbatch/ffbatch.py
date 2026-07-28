import sys
import signal
import math
import argparse
from pathlib import Path
from ffbatch.myconsole import MyConsole
from .presetloader import PresetLoader
from .job import Job, JobFactory
from .scheduler import Scheduler


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
    parser.add_argument('-F', action='store_true', help='read input files paths from text file')
    parser.add_argument('-v', action='store_true', help='show debug output on console')
    parser.add_argument('-c', action='store_true', help='clone folder structure of input files.\
                        For every input directory the internal folder structure is cloned inside the output directory.')
    parser.add_argument('-R', metavar='RELATIVE', help='use in conjunction with the -c option to force the parent directory from where to clone the structure.')
    parser.add_argument('-p', metavar='PRESET', help='preset to use for file conversion')
    parser.add_argument('-i', metavar='INPUT', nargs='+', help="input file paths or directories to be evaluated. Can be relative to the current directory or absolute.\
                        If the -F option is set the input files are interpreted as text files where every line is a path to process.", required=True)
    parser.add_argument('-o', metavar='OUTPUT', help='output directory where to store converted files', required=True)

    args = vars(parser.parse_args())

    # Register interrupt handler for ctrl + c
    signal.signal(signal.SIGINT, signal_handler)

    console = MyConsole()
    console.verbose_enabled = args['v']

    console.verbose('\nInput parameters:')
    console.verbose(f'  INPUT .....: {args['i']}')
    console.verbose(f'  OUTPUT ....: {args['o']}')
    console.verbose(f'  RELATIVE ..: {args['R']}')
    console.verbose(f'  Recursive .: {args['r']}')
    console.verbose(f'  verbose ...: {args['v']}')
    console.verbose(f'  clone .....: {args['c']}')
    console.verbose(f'  Force .....: {args['f']}')
    console.verbose(f'  Preset ....: {args['p']}')
    console.verbose(f'  File Input : {args['F']}')

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
    try:
        jobs = jobFactory.get_jobs_list()
    except ValueError as e:
        console.error(e)

    if jobs.count == 0:
        console.error('no valid input file specified')

    # Print the list of files to be converted and ask if OK to continue
    print_job_list(console, jobs)
    if len([x for x in jobs if x.action == Job.Action.Create or x.action == Job.Action.Overwrite]) == 0:
        return

    if ask_for_confirmation(console):
        Scheduler(console).run(jobs)


def signal_handler(sig, frame):
    print('\nConversion terminated by USER')
    sys.exit(0)


def print_job_list(console : MyConsole, jobs : list[Job]):
    files_to_create = 0
    files_to_overwrite = 0
    files_to_skip = 0

    if len(jobs) == 0:
        number_of_digits = 1
    else:
        number_of_digits = math.ceil(math.log10(len(jobs)))

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


if __name__ == "__main__":
   main()