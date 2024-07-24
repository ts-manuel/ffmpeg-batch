################################################################################################
#  File: ffmpeg-batch.py
#
#
# Preset format:
#   presets are stored in the 'presets.json' file as a dictionary,
#   every entry has a name an the associated ffmpeg command.
#   The script substitutes the placeholder "*.*" with the input file path
#   and the placeholder "*." with the output file path.
#   The file extension of the output is specified in the preset.
#
#   Example:
#   {
#      "Preset 1": "-i *.* ... *.m2ts",
#      "Preset 2": "-i *.* ... *.avi"
#   }
#
#
# Allowed file path combinations:
#     -i specifies the input file / directory, if the input is a directory all the files inside are evaluated.
#        The -r optional parameter can be specified to make the evaluation recursive.
#
#     -o specifies the output directory. All the evaluated input files are converted and stored in this directory
#        the file extension is thaken from the preset (Example: *.mp4)
#
################################################################################################

import signal
import math
import argparse
import json
from pathlib import Path
from dataclasses import dataclass
from ffmpeg import FFmpeg, FFmpegAlreadyExecuted, FFmpegFileNotFound, FFmpegInvalidCommand, FFmpegUnsupportedCodec



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
    parser.add_argument('-f', '--force', action='store_true', help='do not skip already existing output files')
    parser.add_argument('-p', '--preset', help='preset to use for file conversion')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-i', '--input', nargs='+', help='input file paths or directories to be evaluated')
    parser.add_argument('-o', '--output', help='output directory where to store converted files')
    
    args = parser.parse_args()

    # Register interrup handler for ctrl + c
    signal.signal(signal.SIGINT, signal_handler)

    global gVerbose
    gVerbose = args.verbose

    vprint('Input parameters:')
    vprint('  args.input : ' + str(args.input))
    vprint('  args.input : ' + str(args.output))
    vprint('  Recursive .: ' + str(args.r))
    vprint('  Verbose ...: ' + str(gVerbose))
    vprint('  Force .....: ' + str(args.force))
    vprint('  Preset ....: ' + str(args.preset))
    vprint()

    # Load presets
    with open(gPresetsFile, 'r') as f:
        presets = json.load(f)

    #TODO Add parsing with error checking for presets file

    # Check if preset is specified
    if args.preset == None:
        print('Error: no preset specified, use the -p option to slect one of the following presets:')
        for x in presets:
            print(' - {0}'.format(x))
        exit(1)

    # Check if output path exists
    outputDirectory = Path(args.output)
    if not outputDirectory.is_dir():
        print('Error: output path "{0}" does not exist, create output path before running the script'.format(args.output))
        exit(1)

    preset = presets[args.preset]
    outFileExtension = extractOutputFileExtension(preset)

    # Generate a list with all input file paths
    inputFileList = getInputPathsFromInputList(args.input, args.r)

    # Parse the input list and generate a list of tuples (inputPath, outputPath) for every file to be processed 
    targetList = generateTargetList(inputFileList, args.output, outFileExtension)

    # Remove fome the list the output files that already exist if the force flag is not set
    if not args.force:
        flagExistingOutputFiles(targetList)

    if len(targetList) == 0:
        print('Error: no valid input file specified')
        exit(1)

    # Print the list of files to be converted and ask if OK to continue
    if printFilesToConvertAndAskForConfirmation(targetList):
        # Do the conversion
        doConvert(targetList, preset)



def signal_handler(sig, frame):
    print("Conversion terminated by USER")
    exit(0)



def extractOutputFileExtension(preset):
    #extension = preset[preset.rfind('*.') + 1:]
    extension = preset["output_file_ext"]
    return extension



def generateTargetList(inputFileList, output, outFileExtension):
    targetList = []

    vprint('Generating input - output tuples')

    for x in inputFileList:
        if len(x.parents) == 1:
            outPath = Path(output).joinpath(x).with_suffix(outFileExtension)
        else:
            outPath = Path(output).joinpath(x.relative_to(*x.parts[:2])).with_suffix(outFileExtension)

        vprint('  appending path with {0} parents: {1}'.format(len(x.parents), Target(x, outPath)))
        targetList.append(Target(x, outPath))

    return targetList



def flagExistingOutputFiles(targetList):
    for target in targetList:
        if target.outputPath.exists():
            vprint('File already exists: {0}'.format(target))
            target.doConvert = False



def getInputPathsFromInputList(inputList, recursive):
    inputFilePathList = []

    vprint('Generating input file map')

    for inPath in inputList:
        pt = Path(inPath)

        if pt.is_file():
            vprint('  Adding file: [{0}]'.format(inPath))
            inputFilePathList.append(pt)
            
        elif pt.is_dir():
            vprint('  Adding directory: [{0}]'.format(inPath))
            inputFilePathList.extend(getListOfFilesInDirectory(pt, recursive))

        else:
            print('Error: input path "{0}" does not exist'.format(inPath))
            exit(1)

    return inputFilePathList



def getListOfFilesInDirectory(rootPath, recursive):
    fileList = []
    rd = rootPath.glob('*')

    # Test every entry to see if it is a file or a directory
    for x in rd:
        if x.is_file():
            vprint('  Adding file: [{0}]'.format(x))
            fileList.append(x)

        elif x.is_dir() and recursive:
            vprint('  Adding directory: [{0}]'.format(x))
            fileList.extend(getListOfFilesInDirectory(x, recursive))

    return fileList



def printFilesToConvertAndAskForConfirmation(targetList):
    targetCount = len(targetList)
    numberOfDigits = math.ceil(math.log10(targetCount))
    filesToConvert = 0

    print('Files to be converted:')

    # Print list of files to be converted
    for i in range(targetCount):
        tp = targetList[i]
        if tp.doConvert:
            print('[{0:0{n}}]: Input : {1}'.format(filesToConvert, str(tp.inputPath), n=numberOfDigits))
            print('{0:{n}}Output: {1}'.format(' ', str(tp.outputPath),  n=(numberOfDigits + 4)))
            filesToConvert = filesToConvert + 1

    print('\nConverting {0} files'.format(filesToConvert))

    # Ask for confirmation and whait for valid response
    result = ''
    while result != 'y' and result != 'n':
        result = input('Do you want to continue? [Y/n] ')
    print()

    return result == 'y'



def doConvert(targetList, preset):
    for target in targetList:
        if target.doConvert:

            print('Converting {0}'.format(str(target.inputPath)))

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

                vprint(f"Running ffmpeg with: {ffmpeg.arguments}")
                
                ffmpeg.execute()

            except FFmpegAlreadyExecuted as exception:
                print("An exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)
            except FFmpegFileNotFound as exception:
                print("An exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)
            except FFmpegInvalidCommand as exception:
                print("An exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)
            except FFmpegUnsupportedCodec as exception:
                print("An exception has been occurred!")
                print("- Message from ffmpeg:", exception.message)
                print("- Arguments to execute ffmpeg:", exception.arguments)



def vprint(s = ''):
    if gVerbose: print(s)



if __name__ == "__main__":
   main()