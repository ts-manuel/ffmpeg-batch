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



# Global variables
gVerbose = False
gPresetsFile = 'presets.json'



@dataclass
class Target:
    inputPath: Path
    outputPath: Path
    doConvert: bool = True



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

    global gVerbose
    gVerbose = args.v

    vprint('\nInput parameters:')
    vprint(f'  args.input : {args.i}')
    vprint(f'  args.input : {args.o}')
    vprint(f'  Recursive .: {args.r}')
    vprint(f'  Verbose ...: {gVerbose}')
    vprint(f'  Force .....: {args.f}')
    vprint(f'  Preset ....: {args.p}')

    # Check if output path exists
    outputDirectory = Path(args.o)
    if not outputDirectory.is_dir():
        print(f'\nError: output path "{args.o}" does not exist, create output path before running the script')
        exit(1)

    # Assert that a valid preset is specified and get its entry by name
    preset = assertAndGetValidPreset(args.p)

    # Generate list of target files to convert
    targetList = generateTargetList(args.i, args.o, args.r, args.f, preset)

    if len(targetList) == 0:
        print('\nError: no valid input file specified')
        exit(1)

    # Print the list of files to be converted and ask if OK to continue
    if printFilesToConvertAndAskForConfirmation(targetList):
        # Do the conversion
        doConvert(targetList, preset)



def signal_handler(sig, frame):
    print('\nConversion terminated by USER')
    exit(0)



def assertAndGetValidPreset(presetName : str) -> dict:
    with open(gPresetsFile, 'r') as f:
        presets = json.load(f)

    # Check if the preset argument is pecified ad is a valid preset name
    if presetName == None or not presetName in presets:
        print('\nError: no valid preset specified, use the -p option to slect one of the following presets:')
        printAvailablePresets()
        exit(1)

    # Check if the preset contains the required key fields
    preset = presets[presetName]
    keywordsToCeck = ['output_file_ext', 'ffmpeg_args']
    keyNotFound = False

    for k in keywordsToCeck:
        if not k in preset:
            print(f'\nError: wrong sintax in preset file: {gPresetsFile}, keyword "{k}" not set for preset "{presetName}"')
            keyNotFound = True

    if keyNotFound:
        exit()

    return preset



def printAvailablePresets():
    with open(gPresetsFile, 'r') as f:
        presets = json.load(f)

    for p in presets:
        print(f' - {p}')



def generateTargetList(inputList : list[str], output : str, recursive : bool, force : bool, preset : dict) -> list[Target]:
    targetList = []
    outFileExtension = preset['output_file_ext']

    vprint('\nGenerating target list:')

    def generateTarget(inputDir : Path, outputDir: Path, inputPath : Path, fileExt : str, force : bool) -> Target:
            op = outputDir.joinpath(inputPath.relative_to(inputDir)).with_suffix(fileExt)
            dc = not op.exists() or force
            tg = Target(inputPath, op, dc)
            vprint(f'  generated target: {tg}')
            return tg

    for inPath in inputList:
        pt = Path(inPath)

        if pt.is_file():
            vprint(f'  Adding file: [{inPath}]')
            targetList.append(generateTarget(pt.parents[0], Path(output), pt, outFileExtension, force))

        elif pt.is_dir():
            vprint(f'  Adding directory: [{inPath}]')
            ip = getListOfFilesInDirectory(pt, recursive)

            for i in ip:
                targetList.append(generateTarget(pt, Path(output), i, outFileExtension, force))

        else:
            print(f'\nError: input path "{inPath}" does not exist')
            exit(1)

    return targetList



def getListOfFilesInDirectory(rootPath : Path, recursive : bool) -> list[Path]:
    fileList = []
    rd = rootPath.glob('*')

    # Test every entry to see if it is a file or a directory
    for x in rd:
        if x.is_file():
            vprint(f'  Adding file: [{x}]')
            fileList.append(x)

        elif x.is_dir() and recursive:
            vprint(f'  Adding directory: [{x}]')
            fileList.extend(getListOfFilesInDirectory(x, recursive))

    return fileList



def printFilesToConvertAndAskForConfirmation(targetList : list[Target]) -> bool:
    targetCount = len(targetList)
    numberOfDigits = math.ceil(math.log10(targetCount))
    filesToConvert = 0

    print('\nFiles to be converted:')

    # Print list of files to be converted
    for i in range(targetCount):
        tp = targetList[i]
        if tp.doConvert:
            print('[{0:0{n}}]: Input : {1}'.format(filesToConvert, str(tp.inputPath), n=numberOfDigits))
            print('{0:{n}}Output: {1}'.format(' ', str(tp.outputPath),  n=(numberOfDigits + 4)))
            filesToConvert = filesToConvert + 1

    print(f'\nConverting {filesToConvert} files')

    # Ask for confirmation and whait for valid response
    result = ''
    while result != 'y' and result != 'n':
        result = input('Do you want to continue? [Y/n] ')
    print()

    return result == 'y'



def doConvert(targetList : list[Target], preset : dict):
    convProgress = RichProgress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        TextColumn("[yellow]fps: {task.fields[fps]}"),
        TextColumn("[yellow]size: {task.fields[size]}"),
        TextColumn("[yellow]speed: {task.fields[speed]}x"),
        transient=True
    )

    overallProgress = RichProgress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        transient=True
    )

    group = Group(
        convProgress,
        overallProgress
    )

    live = Live(group)

    with live:
        accumulatedTime = 0
        totalTimeSec = getVideoListDuratioInSec([x.inputPath for x in targetList if x.doConvert])
        overallTaskID = overallProgress.add_task("[red]Progress...", total=totalTimeSec)
        convTaskList = []

        for target in targetList:

            # Skip this target if the doConvert flag is not set
            if not target.doConvert:
                continue

            # Create output directory if doesn't exist
            target.outputPath.parent.mkdir(parents=True, exist_ok=True)

            duratioInSec = getVideoDuratioInSec(target.inputPath)

            convTaskList.append(convProgress.add_task(f"[yellow]{target.outputPath.name}", total=duratioInSec, fps=0, speed=0, size=0))

            try:
                ffmpeg = (
                    FFmpeg()
                    .option("y")
                    .input(str(target.inputPath))
                    .output(
                        str(target.outputPath),
                        options=preset["ffmpeg_args"]
                    )
                )

                @ffmpeg.on("progress")
                def on_progress(progress: Progress):
                    convProgress.update(convTaskList[-1], completed=progress.time.seconds, fps=progress.fps, speed=progress.speed, size=HurryFileSize(progress.size))
                    overallProgress.update(overallTaskID, completed=accumulatedTime + progress.time.seconds)

                @ffmpeg.on("completed")
                def on_completed():
                    convProgress.update(convTaskList[-1], completed=duratioInSec)
                    nonlocal accumulatedTime
                    accumulatedTime += duratioInSec

                vprint(f"\nRunning ffmpeg with: {ffmpeg.arguments}")

                ffmpeg.execute()

            except FFmpegError as exception:
                print("\nAn exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)

        overallProgress.update(overallTaskID, completed=totalTimeSec)



def getVideoListDuratioInSec(targetList : list[Path]) -> float:
    duration = float(0)

    vprint(f'\nGet video duration for list of {len(targetList)} items:')

    for x in targetList:
        vprint(f'  getting duration for {x}')
        duration += getVideoDuratioInSec(x)

    return duration



def getVideoDuratioInSec(path : Path) -> float:
    ffprobe = FFmpeg(executable="ffprobe").input(
        str(path),
        print_format="json", # ffprobe will output the results in JSON format
        show_streams=None,
    )

    media = json.loads(ffprobe.execute())

    return float(media['streams'][0]['duration'])



def vprint(s = ''):
    if gVerbose: print(s)



if __name__ == "__main__":
   main()